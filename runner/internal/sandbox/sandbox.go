// Package sandbox runs a single untrusted process under resource limits.
//
// Limits are applied with prlimit(1) (which execs the target, so rusage of the
// child is the target's own), the process is placed in its own process group
// so the whole tree can be killed, and it can optionally be switched to an
// unprivileged UID/GID with supplementary groups cleared.
package sandbox

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"math"
	"os/exec"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

type Limits struct {
	CPUTime      time.Duration // RLIMIT_CPU (rounded up to whole seconds)
	WallTime     time.Duration // hard wall-clock deadline
	AddressSpace int64         // RLIMIT_AS in bytes; 0 = unlimited
	MaxProcesses int           // RLIMIT_NPROC; 0 = unlimited (per UID!)
	MaxFileSize  int64         // RLIMIT_FSIZE in bytes; 0 = unlimited
	StackSize    int64         // RLIMIT_STACK in bytes; 0 = inherit
	MaxOutput    int           // stdout bytes kept; process killed on overflow
	MaxStderr    int           // stderr bytes kept (no kill)
}

type Spec struct {
	Args   []string
	Dir    string
	Stdin  []byte
	Env    []string
	UID    int // < 0 keeps the current user
	GID    int
	Limits Limits
}

type Result struct {
	Stdout         []byte
	Stderr         []byte
	OutputExceeded bool
	ExitCode       int
	Signal         syscall.Signal // 0 when the process exited normally
	TimedOut       bool           // killed by the wall-clock deadline
	CPUTime        time.Duration
	WallTime       time.Duration
	MaxRSSKB       int64
}

// capWriter keeps at most max bytes and reports overflow once.
type capWriter struct {
	mu       sync.Mutex
	buf      bytes.Buffer
	max      int
	exceeded bool
	onExceed func()
}

func (w *capWriter) Write(p []byte) (int, error) {
	w.mu.Lock()
	room := w.max - w.buf.Len()
	if len(p) <= room {
		w.buf.Write(p)
		w.mu.Unlock()
		return len(p), nil
	}
	if room > 0 {
		w.buf.Write(p[:room])
	}
	first := !w.exceeded
	w.exceeded = true
	w.mu.Unlock()
	if first && w.onExceed != nil {
		w.onExceed()
	}
	return len(p), nil // keep draining so the child never blocks on a full pipe
}

func (w *capWriter) result() ([]byte, bool) {
	w.mu.Lock()
	defer w.mu.Unlock()
	return append([]byte(nil), w.buf.Bytes()...), w.exceeded
}

func prlimitArgs(l Limits, target []string) []string {
	cpu := int(math.Ceil(l.CPUTime.Seconds()))
	if cpu < 1 {
		cpu = 1
	}
	args := []string{"prlimit",
		fmt.Sprintf("--cpu=%d:%d", cpu, cpu+1),
		"--core=0",
		"--nofile=64",
	}
	if l.AddressSpace > 0 {
		args = append(args, fmt.Sprintf("--as=%d", l.AddressSpace))
	}
	if l.MaxProcesses > 0 {
		args = append(args, fmt.Sprintf("--nproc=%d", l.MaxProcesses))
	}
	if l.MaxFileSize > 0 {
		args = append(args, fmt.Sprintf("--fsize=%d", l.MaxFileSize))
	}
	if l.StackSize > 0 {
		args = append(args, fmt.Sprintf("--stack=%d", l.StackSize))
	}
	args = append(args, "--")
	return append(args, target...)
}

// Run executes spec and blocks until the process (group) is gone. The
// returned error is non-nil only for infrastructure failures (e.g. the
// binary could not be started); program failures are reported in Result.
func Run(ctx context.Context, s Spec) (Result, error) {
	if len(s.Args) == 0 {
		return Result{}, errors.New("sandbox: empty command")
	}
	if s.Limits.WallTime <= 0 {
		s.Limits.WallTime = 10 * time.Second
	}
	if s.Limits.MaxOutput <= 0 {
		s.Limits.MaxOutput = 1 << 20
	}
	if s.Limits.MaxStderr <= 0 {
		s.Limits.MaxStderr = 64 << 10
	}

	args := prlimitArgs(s.Limits, s.Args)
	cmd := exec.Command(args[0], args[1:]...)
	cmd.Dir = s.Dir
	cmd.Env = s.Env
	cmd.Stdin = bytes.NewReader(s.Stdin)
	cmd.WaitDelay = 250 * time.Millisecond // don't hang on pipes held by orphans

	var pgid atomic.Int64
	kill := func() {
		if p := pgid.Load(); p > 0 {
			_ = syscall.Kill(-int(p), syscall.SIGKILL)
		}
	}
	stdout := &capWriter{max: s.Limits.MaxOutput, onExceed: kill}
	stderr := &capWriter{max: s.Limits.MaxStderr}
	cmd.Stdout, cmd.Stderr = stdout, stderr

	attr := &syscall.SysProcAttr{Setpgid: true, Pdeathsig: syscall.SIGKILL}
	if s.UID >= 0 {
		attr.Credential = &syscall.Credential{
			Uid: uint32(s.UID), Gid: uint32(s.GID), Groups: []uint32{},
		}
	}
	cmd.SysProcAttr = attr

	start := time.Now()
	if err := cmd.Start(); err != nil {
		return Result{}, fmt.Errorf("sandbox: start: %w", err)
	}
	pgid.Store(int64(cmd.Process.Pid))
	if _, exceeded := stdout.result(); exceeded {
		kill() // overflowed before we knew the pgid
	}

	var timedOut atomic.Bool
	timer := time.AfterFunc(s.Limits.WallTime, func() { timedOut.Store(true); kill() })
	stopCtx := context.AfterFunc(ctx, kill)

	waitErr := cmd.Wait()
	wall := time.Since(start)
	timer.Stop()
	stopCtx()
	kill() // reap anything left in the group

	res := Result{TimedOut: timedOut.Load(), WallTime: wall}
	res.Stdout, res.OutputExceeded = stdout.result()
	res.Stderr, _ = stderr.result()

	ps := cmd.ProcessState
	if ps == nil {
		return res, fmt.Errorf("sandbox: wait: %w", waitErr)
	}
	if ws, ok := ps.Sys().(syscall.WaitStatus); ok && ws.Signaled() {
		res.Signal = ws.Signal()
		res.ExitCode = 128 + int(res.Signal)
	} else {
		res.ExitCode = ps.ExitCode()
	}
	res.CPUTime = ps.UserTime() + ps.SystemTime()
	if ru, ok := ps.SysUsage().(*syscall.Rusage); ok {
		res.MaxRSSKB = ru.Maxrss // kilobytes on Linux
	}
	return res, nil
}

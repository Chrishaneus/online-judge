// Package executor compiles a submission once and runs it against a batch of
// inputs, using a fixed pool of worker slots that each own a sandbox UID.
package executor

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"time"

	"github.com/online-judge/oj-runner/internal/lang"
	"github.com/online-judge/oj-runner/internal/sandbox"
)

// Per-test statuses.
const (
	StatusOK  = "OK"
	StatusTLE = "TLE"
	StatusMLE = "MLE"
	StatusOLE = "OLE"
	StatusRE  = "RE"
	// StatusCE is only used as the overall response status.
	StatusCE = "CE"
)

const (
	MaxTests       = 200
	MaxSourceBytes = 256 << 10
	MinTimeLimitMs = 100
	MaxTimeLimitMs = 15_000
	MinMemoryMB    = 16
	MaxMemoryMB    = 1024
)

type TestInput struct {
	ID    string `json:"id"`
	Stdin string `json:"stdin"`
}

type Request struct {
	Language      string      `json:"language"`
	Source        string      `json:"source"`
	Tests         []TestInput `json:"tests"`
	TimeLimitMs   int         `json:"time_limit_ms"`
	MemoryLimitMB int         `json:"memory_limit_mb"`
}

type TestResult struct {
	ID       string `json:"id"`
	Status   string `json:"status"`
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
	ExitCode int    `json:"exit_code"`
	TimeMs   int    `json:"time_ms"`
	MemoryKB int64  `json:"memory_kb"`
}

type Response struct {
	Status        string       `json:"status"`
	CompileOutput string       `json:"compile_output"`
	Results       []TestResult `json:"results"`
}

// ValidationError marks a client error in the request.
type ValidationError struct{ Msg string }

func (e *ValidationError) Error() string { return e.Msg }

type Config struct {
	SandboxRoot    string
	Workers        int
	UIDBase        int
	UseCredentials bool // switch to per-slot UIDs (requires root)
	MaxOutputBytes int
}

type Executor struct {
	cfg   Config
	slots chan int
}

func New(cfg Config) (*Executor, error) {
	if cfg.Workers <= 0 {
		cfg.Workers = 1
	}
	if cfg.MaxOutputBytes <= 0 {
		cfg.MaxOutputBytes = 1 << 20
	}
	if cfg.SandboxRoot == "" {
		cfg.SandboxRoot = filepath.Join(os.TempDir(), "oj-sandbox")
	}
	if err := os.MkdirAll(cfg.SandboxRoot, 0o711); err != nil {
		return nil, fmt.Errorf("create sandbox root: %w", err)
	}
	// 0711: sandboxed users may traverse to their own dir but not list others.
	if err := os.Chmod(cfg.SandboxRoot, 0o711); err != nil {
		return nil, err
	}
	e := &Executor{cfg: cfg, slots: make(chan int, cfg.Workers)}
	for i := 0; i < cfg.Workers; i++ {
		e.slots <- i
	}
	return e, nil
}

// Workers returns the configured number of concurrent slots.
func (e *Executor) Workers() int { return e.cfg.Workers }

func clamp(v, lo, hi, def int) int {
	if v <= 0 {
		return def
	}
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

func (e *Executor) validate(req *Request) (lang.Language, error) {
	l, ok := lang.Get(req.Language)
	if !ok {
		return l, &ValidationError{fmt.Sprintf("unsupported language %q", req.Language)}
	}
	if req.Source == "" {
		return l, &ValidationError{"source is required"}
	}
	if len(req.Source) > MaxSourceBytes {
		return l, &ValidationError{fmt.Sprintf("source exceeds %d bytes", MaxSourceBytes)}
	}
	if len(req.Tests) == 0 {
		return l, &ValidationError{"at least one test is required"}
	}
	if len(req.Tests) > MaxTests {
		return l, &ValidationError{fmt.Sprintf("at most %d tests per request", MaxTests)}
	}
	req.TimeLimitMs = clamp(req.TimeLimitMs, MinTimeLimitMs, MaxTimeLimitMs, 2000)
	req.MemoryLimitMB = clamp(req.MemoryLimitMB, MinMemoryMB, MaxMemoryMB, 256)
	return l, nil
}

// Execute compiles and runs req. It blocks while all slots are busy.
func (e *Executor) Execute(ctx context.Context, req Request) (Response, error) {
	l, err := e.validate(&req)
	if err != nil {
		return Response{}, err
	}

	var slot int
	select {
	case slot = <-e.slots:
	case <-ctx.Done():
		return Response{}, ctx.Err()
	}
	defer func() { e.slots <- slot }()

	uid, gid := -1, -1
	if e.cfg.UseCredentials {
		uid, gid = e.cfg.UIDBase+slot, e.cfg.UIDBase+slot
		defer killAllOf(uid)
	}

	dir, err := os.MkdirTemp(e.cfg.SandboxRoot, fmt.Sprintf("slot%d-", slot))
	if err != nil {
		return Response{}, fmt.Errorf("create work dir: %w", err)
	}
	defer os.RemoveAll(dir)
	srcPath := filepath.Join(dir, l.SourceFile)
	if err := os.WriteFile(srcPath, []byte(req.Source), 0o600); err != nil {
		return Response{}, err
	}
	if err := os.Chmod(dir, 0o700); err != nil {
		return Response{}, err
	}
	if uid >= 0 {
		if err := os.Chown(dir, uid, gid); err != nil {
			return Response{}, fmt.Errorf("chown work dir: %w", err)
		}
		if err := os.Chown(srcPath, uid, gid); err != nil {
			return Response{}, err
		}
	}

	env := []string{
		"PATH=/usr/local/bin:/usr/bin:/bin",
		"HOME=" + dir,
		"TMPDIR=" + dir,
		"LANG=C.UTF-8",
		"PYTHONDONTWRITEBYTECODE=1",
	}
	maxProcs := 0
	if uid >= 0 {
		maxProcs = 64 // RLIMIT_NPROC is per-UID, only meaningful with our own UIDs
	}

	if l.Compile != nil {
		cr, err := sandbox.Run(ctx, sandbox.Spec{
			Args: l.Compile, Dir: dir, Env: env, UID: uid, GID: gid,
			Limits: sandbox.Limits{
				CPUTime:      20 * time.Second,
				WallTime:     30 * time.Second,
				MaxProcesses: maxProcs,
				MaxFileSize:  64 << 20,
				MaxOutput:    32 << 10,
				MaxStderr:    32 << 10,
			},
		})
		if err != nil {
			return Response{}, err
		}
		if cr.ExitCode != 0 || cr.TimedOut {
			out := string(bytes.TrimSpace(append(cr.Stderr, cr.Stdout...)))
			if cr.TimedOut {
				out = "compilation timed out\n" + out
			}
			return Response{Status: StatusCE, CompileOutput: out, Results: []TestResult{}}, nil
		}
	}

	cpuLimit := time.Duration(req.TimeLimitMs) * time.Millisecond
	memLimitKB := int64(req.MemoryLimitMB) * 1024
	limits := sandbox.Limits{
		CPUTime:      cpuLimit,
		WallTime:     2*cpuLimit + time.Second,
		MaxProcesses: maxProcs,
		MaxFileSize:  16 << 20,
		StackSize:    64 << 20,
		MaxOutput:    e.cfg.MaxOutputBytes,
		MaxStderr:    16 << 10,
	}
	if l.LimitAddressSpace {
		// Headroom for shared libraries / interpreter; real usage is judged by RSS.
		limits.AddressSpace = (int64(req.MemoryLimitMB) + 128) << 20
	}

	resp := Response{Status: StatusOK, Results: make([]TestResult, 0, len(req.Tests))}
	for _, tc := range req.Tests {
		if err := ctx.Err(); err != nil {
			return Response{}, err
		}
		r, err := sandbox.Run(ctx, sandbox.Spec{
			Args: l.RunArgs(req.MemoryLimitMB), Dir: dir, Env: env,
			Stdin: []byte(tc.Stdin), UID: uid, GID: gid, Limits: limits,
		})
		if err != nil {
			return Response{}, err
		}
		resp.Results = append(resp.Results, TestResult{
			ID:       tc.ID,
			Status:   classify(r, cpuLimit, memLimitKB),
			Stdout:   string(r.Stdout),
			Stderr:   string(r.Stderr),
			ExitCode: r.ExitCode,
			TimeMs:   int(r.CPUTime.Milliseconds()),
			MemoryKB: r.MaxRSSKB,
		})
	}
	return resp, nil
}

var oomMarkers = [][]byte{
	[]byte("MemoryError"),
	[]byte("std::bad_alloc"),
	[]byte("JavaScript heap out of memory"),
}

func classify(r sandbox.Result, cpuLimit time.Duration, memLimitKB int64) string {
	switch {
	case r.OutputExceeded:
		return StatusOLE
	case r.TimedOut || r.Signal == syscall.SIGXCPU || r.CPUTime > cpuLimit:
		return StatusTLE
	case r.MaxRSSKB > memLimitKB:
		return StatusMLE
	case r.ExitCode != 0:
		for _, m := range oomMarkers {
			if bytes.Contains(r.Stderr, m) {
				return StatusMLE
			}
		}
		return StatusRE
	}
	return StatusOK
}

// killAllOf kills every process owned by uid, including ones that escaped
// the process group via setsid. kill(-1) from a process running as uid
// signals all processes of that uid (except itself).
func killAllOf(uid int) {
	cmd := exec.Command("sh", "-c", "kill -9 -1 2>/dev/null; true")
	// Runs as the sandbox UID: never hand it the runner's environment.
	cmd.Env = []string{"PATH=/usr/bin:/bin"}
	cmd.SysProcAttr = &syscall.SysProcAttr{
		Credential: &syscall.Credential{Uid: uint32(uid), Gid: uint32(uid), Groups: []uint32{}},
	}
	_ = cmd.Run()
}

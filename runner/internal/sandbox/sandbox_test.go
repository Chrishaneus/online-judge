package sandbox

import (
	"context"
	"os/exec"
	"strings"
	"syscall"
	"testing"
	"time"
)

func requirePrlimit(t *testing.T) {
	t.Helper()
	if _, err := exec.LookPath("prlimit"); err != nil {
		t.Skip("prlimit not available")
	}
}

func spec(args ...string) Spec {
	return Spec{
		Args: args, Dir: "/tmp", UID: -1,
		Env:    []string{"PATH=/usr/bin:/bin"},
		Limits: Limits{CPUTime: time.Second, WallTime: 3 * time.Second},
	}
}

func TestEchoAndStdin(t *testing.T) {
	requirePrlimit(t)
	s := spec("sh", "-c", "read x; echo got:$x; echo err >&2")
	s.Stdin = []byte("42\n")
	r, err := Run(context.Background(), s)
	if err != nil {
		t.Fatal(err)
	}
	if string(r.Stdout) != "got:42\n" || string(r.Stderr) != "err\n" || r.ExitCode != 0 {
		t.Fatalf("unexpected result %+v", r)
	}
}

func TestExitCode(t *testing.T) {
	requirePrlimit(t)
	r, err := Run(context.Background(), spec("sh", "-c", "exit 3"))
	if err != nil {
		t.Fatal(err)
	}
	if r.ExitCode != 3 || r.Signal != 0 {
		t.Fatalf("exit=%d signal=%v", r.ExitCode, r.Signal)
	}
}

func TestWallTimeout(t *testing.T) {
	requirePrlimit(t)
	s := spec("sleep", "10")
	s.Limits.WallTime = 300 * time.Millisecond
	start := time.Now()
	r, err := Run(context.Background(), s)
	if err != nil {
		t.Fatal(err)
	}
	if !r.TimedOut || r.Signal != syscall.SIGKILL {
		t.Fatalf("expected timeout kill, got %+v", r)
	}
	if time.Since(start) > 2*time.Second {
		t.Fatal("timeout took too long")
	}
}

func TestCPULimit(t *testing.T) {
	requirePrlimit(t)
	s := spec("sh", "-c", "while :; do :; done")
	s.Limits.WallTime = 5 * time.Second
	r, err := Run(context.Background(), s)
	if err != nil {
		t.Fatal(err)
	}
	if r.Signal != syscall.SIGXCPU && r.Signal != syscall.SIGKILL {
		t.Fatalf("expected CPU limit signal, got %+v", r)
	}
	if r.CPUTime < 900*time.Millisecond {
		t.Fatalf("cpu time %v too small", r.CPUTime)
	}
}

func TestOutputLimitKills(t *testing.T) {
	requirePrlimit(t)
	s := spec("yes")
	s.Limits.MaxOutput = 1024
	r, err := Run(context.Background(), s)
	if err != nil {
		t.Fatal(err)
	}
	if !r.OutputExceeded || len(r.Stdout) != 1024 || r.TimedOut {
		t.Fatalf("expected OLE kill, got exceeded=%v len=%d timedOut=%v", r.OutputExceeded, len(r.Stdout), r.TimedOut)
	}
}

func TestAddressSpaceLimit(t *testing.T) {
	requirePrlimit(t)
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}
	s := spec("python3", "-c", "x = bytearray(512*1024*1024)")
	s.Limits.AddressSpace = 128 << 20
	r, err := Run(context.Background(), s)
	if err != nil {
		t.Fatal(err)
	}
	if r.ExitCode == 0 || !strings.Contains(string(r.Stderr), "MemoryError") {
		t.Fatalf("expected MemoryError, got exit=%d stderr=%s", r.ExitCode, r.Stderr)
	}
}

func TestContextCancel(t *testing.T) {
	requirePrlimit(t)
	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()
	r, err := Run(ctx, spec("sleep", "10"))
	if err != nil {
		t.Fatal(err)
	}
	if r.Signal != syscall.SIGKILL || r.WallTime > 2*time.Second {
		t.Fatalf("expected cancellation kill, got %+v", r)
	}
}

func TestBackgroundChildDoesNotHang(t *testing.T) {
	requirePrlimit(t)
	start := time.Now()
	_, err := Run(context.Background(), spec("sh", "-c", "sleep 30 & echo done"))
	if err != nil {
		t.Fatal(err)
	}
	if time.Since(start) > 2*time.Second {
		t.Fatal("orphaned child kept Run blocked")
	}
}

func TestParentEnvironmentNotInherited(t *testing.T) {
	requirePrlimit(t)
	t.Setenv("OJ_TEST_SECRET", "hunter2")
	for _, env := range [][]string{nil, {"PATH=/usr/bin:/bin"}} {
		s := spec("/usr/bin/env")
		s.Env = env
		r, err := Run(context.Background(), s)
		if err != nil {
			t.Fatal(err)
		}
		if r.ExitCode != 0 {
			t.Fatalf("env failed: %+v", r)
		}
		if strings.Contains(string(r.Stdout), "hunter2") || strings.Contains(string(r.Stdout), "OJ_TEST_SECRET") {
			t.Fatalf("sandboxed process saw the parent's environment (Env=%v):\n%s", env, r.Stdout)
		}
		if env == nil && strings.TrimSpace(string(r.Stdout)) != "" {
			t.Fatalf("nil Env should give an empty environment, got:\n%s", r.Stdout)
		}
	}
}

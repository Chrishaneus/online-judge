package executor

import (
	"context"
	"errors"
	"os"
	"os/exec"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"

	"github.com/online-judge/online-judge/runner/internal/sandbox"
)

func newExec(t *testing.T, workers int) *Executor {
	t.Helper()
	if _, err := exec.LookPath("prlimit"); err != nil {
		t.Skip("prlimit not available")
	}
	e, err := New(Config{SandboxRoot: t.TempDir(), Workers: workers, MaxOutputBytes: 4096})
	if err != nil {
		t.Fatal(err)
	}
	return e
}

func need(t *testing.T, bin string) {
	t.Helper()
	if _, err := exec.LookPath(bin); err != nil {
		t.Skipf("%s not available", bin)
	}
}

func run(t *testing.T, e *Executor, req Request) Response {
	t.Helper()
	resp, err := e.Execute(context.Background(), req)
	if err != nil {
		t.Fatal(err)
	}
	return resp
}

func TestValidation(t *testing.T) {
	e := newExec(t, 1)
	cases := []Request{
		{Language: "cobol", Source: "x", Tests: []TestInput{{}}},
		{Language: "python", Source: "", Tests: []TestInput{{}}},
		{Language: "python", Source: "x"},
		{Language: "python", Source: strings.Repeat("x", MaxSourceBytes+1), Tests: []TestInput{{}}},
		{Language: "python", Source: "x", Tests: make([]TestInput, MaxTests+1)},
	}
	for i, req := range cases {
		_, err := e.Execute(context.Background(), req)
		var ve *ValidationError
		if !errors.As(err, &ve) {
			t.Errorf("case %d: expected ValidationError, got %v", i, err)
		}
	}
}

func TestPythonBatch(t *testing.T) {
	need(t, "python3")
	e := newExec(t, 1)
	resp := run(t, e, Request{
		Language: "python",
		Source:   "a, b = map(int, input().split())\nprint(a + b)\n",
		Tests:    []TestInput{{ID: "1", Stdin: "1 2\n"}, {ID: "2", Stdin: "10 -3\n"}},
	})
	if resp.Status != StatusOK || len(resp.Results) != 2 {
		t.Fatalf("unexpected response %+v", resp)
	}
	if resp.Results[0].Stdout != "3\n" || resp.Results[1].Stdout != "7\n" || resp.Results[1].ID != "2" {
		t.Fatalf("wrong outputs %+v", resp.Results)
	}
	if resp.Results[0].Status != StatusOK || resp.Results[0].MemoryKB == 0 {
		t.Fatalf("bad result metadata %+v", resp.Results[0])
	}
}

func TestPythonCompileError(t *testing.T) {
	need(t, "python3")
	resp := run(t, newExec(t, 1), Request{Language: "python", Source: "def (:\n", Tests: []TestInput{{ID: "1"}}})
	if resp.Status != StatusCE || !strings.Contains(resp.CompileOutput, "SyntaxError") {
		t.Fatalf("expected CE, got %+v", resp)
	}
}

func TestStatuses(t *testing.T) {
	need(t, "python3")
	e := newExec(t, 1)
	cases := map[string]string{
		StatusRE:  "raise SystemExit(3)",
		StatusTLE: "while True: pass",
		StatusOLE: "while True: print('x' * 100)",
		StatusMLE: "x = bytearray(400 * 1024 * 1024)",
	}
	for want, src := range cases {
		resp := run(t, e, Request{Language: "python", Source: src, Tests: []TestInput{{ID: "1"}},
			TimeLimitMs: 500, MemoryLimitMB: 64})
		if got := resp.Results[0].Status; got != want {
			t.Errorf("%q: status %s, want %s (stderr=%q)", src, got, want, resp.Results[0].Stderr)
		}
	}
}

func TestCpp(t *testing.T) {
	need(t, "g++")
	e := newExec(t, 1)
	resp := run(t, e, Request{Language: "cpp",
		Source: "#include <iostream>\nint main(){long long a,b;std::cin>>a>>b;std::cout<<a+b<<\"\\n\";}",
		Tests:  []TestInput{{ID: "1", Stdin: "1000000000 1000000000"}}})
	if resp.Status != StatusOK || resp.Results[0].Stdout != "2000000000\n" {
		t.Fatalf("unexpected %+v", resp)
	}
	resp = run(t, e, Request{Language: "cpp", Source: "int main( { }", Tests: []TestInput{{ID: "1"}}})
	if resp.Status != StatusCE || resp.CompileOutput == "" {
		t.Fatalf("expected CE, got %+v", resp)
	}
}

func TestSlotsLimitConcurrency(t *testing.T) {
	need(t, "python3")
	e := newExec(t, 2)
	var wg sync.WaitGroup
	start := time.Now()
	for i := 0; i < 4; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if _, err := e.Execute(context.Background(), Request{Language: "python",
				Source: "import time; time.sleep(0.3)", Tests: []TestInput{{ID: "1"}}}); err != nil {
				t.Error(err)
			}
		}()
	}
	wg.Wait()
	// 4 jobs, 2 slots, 0.3s each => at least ~0.6s.
	if el := time.Since(start); el < 550*time.Millisecond {
		t.Fatalf("expected serialization through 2 slots, took %v", el)
	}
}

func TestContextCancelledWhileWaiting(t *testing.T) {
	e := newExec(t, 1)
	<-e.slots // occupy the only slot
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	_, err := e.Execute(ctx, Request{Language: "python", Source: "x", Tests: []TestInput{{}}})
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("expected deadline exceeded, got %v", err)
	}
}

func TestClassify(t *testing.T) {
	lim := time.Second
	cases := []struct {
		r    sandbox.Result
		want string
	}{
		{sandbox.Result{}, StatusOK},
		{sandbox.Result{OutputExceeded: true, Signal: syscall.SIGKILL}, StatusOLE},
		{sandbox.Result{TimedOut: true}, StatusTLE},
		{sandbox.Result{Signal: syscall.SIGXCPU}, StatusTLE},
		{sandbox.Result{CPUTime: 2 * time.Second}, StatusTLE},
		{sandbox.Result{MaxRSSKB: 2048}, StatusMLE},
		{sandbox.Result{ExitCode: 134, Stderr: []byte("terminate called after throwing an instance of 'std::bad_alloc'")}, StatusMLE},
		{sandbox.Result{ExitCode: 1}, StatusRE},
	}
	for i, c := range cases {
		if got := classify(c.r, lim, 1024); got != c.want {
			t.Errorf("case %d: got %s want %s", i, got, c.want)
		}
	}
}

func TestWorkDirCleanedUp(t *testing.T) {
	need(t, "python3")
	e := newExec(t, 1)
	run(t, e, Request{Language: "python", Source: "print(1)", Tests: []TestInput{{ID: "1"}}})
	entries, err := os.ReadDir(e.cfg.SandboxRoot)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 0 {
		t.Fatalf("work dirs left behind: %v", entries)
	}
}

// Sandboxed code must never see the runner's environment (it holds the
// broker credentials in RABBITMQ_URL until startup unsets it).
func TestSubmissionCannotSeeParentEnvironment(t *testing.T) {
	need(t, "python3")
	t.Setenv("RABBITMQ_URL", "amqp://runner:s3cret@rabbitmq:5672/")
	resp := run(t, newExec(t, 1), Request{
		Language: "python",
		Source:   "import os\nfor k, v in os.environ.items(): print(k + '=' + v)\n",
		Tests:    []TestInput{{ID: "1"}},
	})
	if resp.Status != StatusOK || resp.Results[0].Status != StatusOK {
		t.Fatalf("unexpected response %+v", resp)
	}
	out := resp.Results[0].Stdout
	if strings.Contains(out, "s3cret") || strings.Contains(out, "RABBITMQ_URL") {
		t.Fatalf("submission saw the parent's environment:\n%s", out)
	}
	if !strings.Contains(out, "PATH=/usr/local/bin:/usr/bin:/bin") {
		t.Fatalf("expected the explicit sandbox environment, got:\n%s", out)
	}
}

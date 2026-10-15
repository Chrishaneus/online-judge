package consumer

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"strings"
	"sync"
	"testing"

	amqp "github.com/rabbitmq/amqp091-go"
	"google.golang.org/protobuf/proto"

	"github.com/online-judge/online-judge/runner/internal/executor"
	ojv1 "github.com/online-judge/online-judge/runner/internal/gen/oj/v1"
	"github.com/online-judge/online-judge/runner/internal/lang"
)

// recorder is a fake AMQP acknowledger and publisher that records every call
// in order, so tests can assert e.g. "finished confirmed, then ack".
type recorder struct {
	mu      sync.Mutex
	calls   []string
	events  []*ojv1.JobEvent
	msgs    []amqp.Publishing
	keys    []string
	failPub map[int]error // publish number (0-based) -> error
}

func (r *recorder) add(c string) { r.mu.Lock(); r.calls = append(r.calls, c); r.mu.Unlock() }

func (r *recorder) Ack(uint64, bool) error { r.add("ack"); return nil }
func (r *recorder) Nack(_ uint64, _ bool, requeue bool) error {
	r.add(fmt.Sprintf("nack(requeue=%v)", requeue))
	return nil
}
func (r *recorder) Reject(_ uint64, requeue bool) error {
	r.add(fmt.Sprintf("reject(requeue=%v)", requeue))
	return nil
}

func (r *recorder) Publish(_ context.Context, key string, msg amqp.Publishing) error {
	r.mu.Lock()
	n := len(r.msgs)
	r.mu.Unlock()
	if err := r.failPub[n]; err != nil {
		r.add("publish-failed")
		r.mu.Lock()
		r.msgs = append(r.msgs, msg)
		r.mu.Unlock()
		return err
	}
	ev := &ojv1.JobEvent{}
	if err := proto.Unmarshal(msg.Body, ev); err != nil {
		panic(err)
	}
	r.mu.Lock()
	r.msgs, r.keys, r.events = append(r.msgs, msg), append(r.keys, key), append(r.events, ev)
	r.mu.Unlock()
	switch ev.GetEvent().(type) {
	case *ojv1.JobEvent_Started:
		r.add("started")
	case *ojv1.JobEvent_Finished:
		r.add("finished")
	default:
		r.add("event?")
	}
	return nil
}

type fakeExec struct {
	resp executor.Response
	err  error
	got  []executor.Request
}

func (f *fakeExec) Execute(_ context.Context, req executor.Request) (executor.Response, error) {
	f.got = append(f.got, req)
	return f.resp, f.err
}

func quietLog() *slog.Logger { return slog.New(slog.NewTextHandler(io.Discard, nil)) }

func newHandler(rec *recorder, ex *fakeExec) *Handler {
	return &Handler{Exec: ex, Pub: rec, RunnerID: "runner-test", Log: quietLog()}
}

func job() *ojv1.ExecuteJob {
	return &ojv1.ExecuteJob{
		JobId: "submission-7", SubmissionId: 7,
		Language: ojv1.Language_LANGUAGE_CPP, Source: "int main(){}",
		Tests:       []*ojv1.TestInput{{Id: "11", Stdin: "1\n"}, {Id: "12", Stdin: "2\n"}},
		TimeLimitMs: 1500, MemoryLimitMb: 64,
	}
}

func delivery(t *testing.T, rec *recorder, j *ojv1.ExecuteJob) amqp.Delivery {
	t.Helper()
	body, err := proto.Marshal(j)
	if err != nil {
		t.Fatal(err)
	}
	return amqp.Delivery{
		Acknowledger: rec, DeliveryTag: 1,
		ContentType: ContentType, Type: TypeJob,
		ReplyTo: "judge.events", CorrelationId: "corr-1",
		Body: body,
	}
}

func assertCalls(t *testing.T, rec *recorder, want ...string) {
	t.Helper()
	if got := strings.Join(rec.calls, " "); got != strings.Join(want, " ") {
		t.Fatalf("calls = %q, want %q", got, strings.Join(want, " "))
	}
}

func okResponse() executor.Response {
	return executor.Response{Status: executor.StatusOK, Results: []executor.TestResult{
		{ID: "11", Status: executor.StatusOK, Stdout: "1\n", ExitCode: 0, TimeMs: 3, MemoryKB: 1000},
		{ID: "12", Status: executor.StatusRE, Stderr: "boom", ExitCode: 3, TimeMs: 4, MemoryKB: 2000},
	}}
}

func TestHandleOK(t *testing.T) {
	rec := &recorder{}
	ex := &fakeExec{resp: okResponse()}
	newHandler(rec, ex).Handle(context.Background(), delivery(t, rec, job()))

	assertCalls(t, rec, "started", "finished", "ack")

	// Request mapping.
	req := ex.got[0]
	if req.Language != "cpp" || req.Source != "int main(){}" || req.TimeLimitMs != 1500 || req.MemoryLimitMB != 64 ||
		len(req.Tests) != 2 || req.Tests[1] != (executor.TestInput{ID: "12", Stdin: "2\n"}) {
		t.Fatalf("bad request %+v", req)
	}

	// AMQP properties and routing.
	for i, m := range rec.msgs {
		if rec.keys[i] != "judge.events" || m.CorrelationId != "corr-1" || m.ContentType != ContentType ||
			m.Type != TypeJobEvent || m.DeliveryMode != amqp.Persistent {
			t.Fatalf("publish %d has wrong properties: key=%q %+v", i, rec.keys[i], m)
		}
	}
	for _, ev := range rec.events {
		if ev.GetJobId() != "submission-7" || ev.GetSubmissionId() != 7 || ev.GetRunnerId() != "runner-test" {
			t.Fatalf("bad event header %v", ev)
		}
	}

	// Result mapping.
	want := &ojv1.ExecuteResult{Status: ojv1.ExecuteStatus_EXECUTE_STATUS_OK, Results: []*ojv1.TestRun{
		{Id: "11", Status: ojv1.RunStatus_RUN_STATUS_OK, Stdout: "1\n", TimeMs: 3, MemoryKb: 1000},
		{Id: "12", Status: ojv1.RunStatus_RUN_STATUS_RUNTIME_ERROR, Stderr: "boom", ExitCode: 3, TimeMs: 4, MemoryKb: 2000},
	}}
	if got := rec.events[1].GetFinished(); !proto.Equal(got, want) {
		t.Fatalf("finished = %v\nwant %v", got, want)
	}
}

func TestHandleCompilationError(t *testing.T) {
	rec := &recorder{}
	ex := &fakeExec{resp: executor.Response{Status: executor.StatusCE, CompileOutput: "main.cpp:1: error", Results: []executor.TestResult{}}}
	newHandler(rec, ex).Handle(context.Background(), delivery(t, rec, job()))

	assertCalls(t, rec, "started", "finished", "ack")
	f := rec.events[1].GetFinished()
	if f.GetStatus() != ojv1.ExecuteStatus_EXECUTE_STATUS_COMPILATION_ERROR || f.GetCompileOutput() != "main.cpp:1: error" || len(f.GetResults()) != 0 {
		t.Fatalf("bad CE result %v", f)
	}
}

func TestHandleRejected(t *testing.T) {
	cases := map[string]func(*ojv1.ExecuteJob){
		"unspecified language": func(j *ojv1.ExecuteJob) { j.Language = ojv1.Language_LANGUAGE_UNSPECIFIED },
		"unknown language":     func(j *ojv1.ExecuteJob) { j.Language = ojv1.Language(99) },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			rec := &recorder{}
			ex := &fakeExec{}
			j := job()
			mutate(j)
			newHandler(rec, ex).Handle(context.Background(), delivery(t, rec, j))

			assertCalls(t, rec, "started", "finished", "ack")
			if len(ex.got) != 0 {
				t.Fatal("executor must not be called for a rejected job")
			}
			f := rec.events[1].GetFinished()
			if f.GetStatus() != ojv1.ExecuteStatus_EXECUTE_STATUS_REJECTED || !strings.Contains(f.GetError(), "language") {
				t.Fatalf("bad rejected result %v", f)
			}
		})
	}

	t.Run("executor validation error", func(t *testing.T) {
		rec := &recorder{}
		ex := &fakeExec{err: &executor.ValidationError{Msg: "at least one test is required"}}
		newHandler(rec, ex).Handle(context.Background(), delivery(t, rec, job()))

		assertCalls(t, rec, "started", "finished", "ack")
		f := rec.events[1].GetFinished()
		if f.GetStatus() != ojv1.ExecuteStatus_EXECUTE_STATUS_REJECTED || f.GetError() != "at least one test is required" {
			t.Fatalf("bad rejected result %v", f)
		}
	})
}

func TestHandleDeadLettersBadMessages(t *testing.T) {
	cases := map[string]func(*amqp.Delivery){
		"wrong type":   func(d *amqp.Delivery) { d.Type = "oj.v1.Something" },
		"missing type": func(d *amqp.Delivery) { d.Type = "" },
		"undecodable":  func(d *amqp.Delivery) { d.Body = []byte{0xff, 0xff, 0xff} },
		"no reply_to":  func(d *amqp.Delivery) { d.ReplyTo = "" },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			rec := &recorder{}
			ex := &fakeExec{resp: okResponse()}
			d := delivery(t, rec, job())
			mutate(&d)
			newHandler(rec, ex).Handle(context.Background(), d)

			assertCalls(t, rec, "nack(requeue=false)")
			if len(ex.got) != 0 {
				t.Fatal("executor must not be called")
			}
		})
	}
}

func TestHandleInfrastructureErrorsRequeue(t *testing.T) {
	t.Run("executor error", func(t *testing.T) {
		rec := &recorder{}
		ex := &fakeExec{err: errors.New("sandbox: start: fork/exec: resource temporarily unavailable")}
		newHandler(rec, ex).Handle(context.Background(), delivery(t, rec, job()))
		assertCalls(t, rec, "started", "nack(requeue=true)")
	})
	t.Run("context cancelled", func(t *testing.T) {
		rec := &recorder{}
		ex := &fakeExec{err: context.Canceled}
		newHandler(rec, ex).Handle(context.Background(), delivery(t, rec, job()))
		assertCalls(t, rec, "started", "nack(requeue=true)")
	})
	t.Run("unknown executor status", func(t *testing.T) {
		rec := &recorder{}
		ex := &fakeExec{resp: executor.Response{Status: "WAT"}}
		newHandler(rec, ex).Handle(context.Background(), delivery(t, rec, job()))
		assertCalls(t, rec, "started", "nack(requeue=true)")
	})
	t.Run("started not confirmed", func(t *testing.T) {
		rec := &recorder{failPub: map[int]error{0: errors.New("nacked")}}
		ex := &fakeExec{resp: okResponse()}
		newHandler(rec, ex).Handle(context.Background(), delivery(t, rec, job()))
		assertCalls(t, rec, "publish-failed", "nack(requeue=true)")
		if len(ex.got) != 0 {
			t.Fatal("executor must not run when started could not be published")
		}
	})
	t.Run("finished not confirmed", func(t *testing.T) {
		rec := &recorder{failPub: map[int]error{1: errors.New("channel closed")}}
		ex := &fakeExec{resp: okResponse()}
		newHandler(rec, ex).Handle(context.Background(), delivery(t, rec, job()))
		assertCalls(t, rec, "started", "publish-failed", "nack(requeue=true)")
	})
}

func TestHandleLastAttemptDeadLetters(t *testing.T) {
	failing := func() *fakeExec { return &fakeExec{err: errors.New("infrastructure failure")} }
	for _, tc := range []struct {
		headers amqp.Table
		want    string
	}{
		{nil, "nack(requeue=true)"},
		{amqp.Table{"x-acquired-count": int64(1)}, "nack(requeue=true)"},
		{amqp.Table{"x-acquired-count": int64(2)}, "nack(requeue=false)"},
		{amqp.Table{"x-delivery-count": int32(2), "x-acquired-count": int64(1)}, "nack(requeue=false)"},
	} {
		rec := &recorder{}
		d := delivery(t, rec, job())
		d.Headers = tc.headers
		newHandler(rec, failing()).Handle(context.Background(), d)
		assertCalls(t, rec, "started", tc.want)
	}

	t.Run("aborted jobs are always requeued", func(t *testing.T) {
		rec := &recorder{}
		d := delivery(t, rec, job())
		d.Headers = amqp.Table{"x-acquired-count": int64(5)}
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		newHandler(rec, &fakeExec{err: context.Canceled}).Handle(ctx, d)
		assertCalls(t, rec, "started", "nack(requeue=true)")
	})
}

func TestLanguageMappingCoversEnum(t *testing.T) {
	for num, name := range ojv1.Language_name {
		l := ojv1.Language(num)
		id, ok := LanguageID(l)
		if l == ojv1.Language_LANGUAGE_UNSPECIFIED {
			if ok {
				t.Fatalf("%s must not map to a language", name)
			}
			continue
		}
		if !ok {
			t.Fatalf("%s has no lang id", name)
		}
		if _, ok := lang.Get(id); !ok {
			t.Fatalf("%s maps to %q, which is not in the lang registry", name, id)
		}
	}
	if len(languageIDs) != len(lang.All()) {
		t.Fatalf("lang registry has %d languages, the enum mapping %d", len(lang.All()), len(languageIDs))
	}
}

func TestRunStatusMapping(t *testing.T) {
	want := map[string]ojv1.RunStatus{
		executor.StatusOK:  ojv1.RunStatus_RUN_STATUS_OK,
		executor.StatusTLE: ojv1.RunStatus_RUN_STATUS_TIME_LIMIT_EXCEEDED,
		executor.StatusMLE: ojv1.RunStatus_RUN_STATUS_MEMORY_LIMIT_EXCEEDED,
		executor.StatusOLE: ojv1.RunStatus_RUN_STATUS_OUTPUT_LIMIT_EXCEEDED,
		executor.StatusRE:  ojv1.RunStatus_RUN_STATUS_RUNTIME_ERROR,
	}
	for s, rs := range want {
		r, err := ToResult(executor.Response{Status: executor.StatusOK, Results: []executor.TestResult{{ID: "1", Status: s}}}, DefaultMaxEventBytes)
		if err != nil {
			t.Fatal(err)
		}
		if got := r.GetResults()[0].GetStatus(); got != rs {
			t.Errorf("%s -> %s, want %s", s, got, rs)
		}
	}
}

func TestToResultOutputBudget(t *testing.T) {
	resp := executor.Response{Status: executor.StatusOK, Results: []executor.TestResult{
		{ID: "1", Status: executor.StatusOK, Stdout: strings.Repeat("a", 60)},
		{ID: "2", Status: executor.StatusOK, Stdout: strings.Repeat("b", 60), TimeMs: 9},
		{ID: "3", Status: executor.StatusTLE, Stdout: "c"},
		{ID: "4", Status: executor.StatusOK},
	}}
	r, err := ToResult(resp, 100)
	if err != nil {
		t.Fatal(err)
	}
	got := r.GetResults()
	if got[0].GetStdout() != resp.Results[0].Stdout || got[0].GetStatus() != ojv1.RunStatus_RUN_STATUS_OK {
		t.Fatalf("test 1 should be untouched: %v", got[0])
	}
	if got[1].GetStdout() != "" || got[1].GetStatus() != ojv1.RunStatus_RUN_STATUS_OUTPUT_LIMIT_EXCEEDED || got[1].GetTimeMs() != 9 {
		t.Fatalf("test 2 should be OLE without output: %v", got[1])
	}
	if got[2].GetStdout() != "" || got[2].GetStatus() != ojv1.RunStatus_RUN_STATUS_TIME_LIMIT_EXCEEDED {
		t.Fatalf("test 3 keeps its own failure: %v", got[2])
	}
	if got[3].GetStatus() != ojv1.RunStatus_RUN_STATUS_OK {
		t.Fatalf("test 4 had no output: %v", got[3])
	}
}

func TestRedact(t *testing.T) {
	err := redact(errors.New("dial amqp://runner:s3cret@rabbitmq:5672/: refused"), "amqp://runner:s3cret@rabbitmq:5672/")
	if strings.Contains(err.Error(), "s3cret") {
		t.Fatalf("password not redacted: %v", err)
	}
}

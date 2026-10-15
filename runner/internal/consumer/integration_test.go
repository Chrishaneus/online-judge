package consumer

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
	"google.golang.org/protobuf/proto"

	"github.com/online-judge/online-judge/runner/internal/executor"
	ojv1 "github.com/online-judge/online-judge/runner/internal/gen/oj/v1"
)

// Integration tests against a real broker. They run only when
// RABBITMQ_TEST_URL is set (a user allowed to declare queues), e.g.
//
//	RABBITMQ_TEST_URL=amqp://oj:oj@127.0.0.1:5673/ go test ./internal/consumer
//
// Each test declares its own uniquely named queues with the arguments from
// runner.proto and deletes them afterwards.

type funcExec func(ctx context.Context, req executor.Request) (executor.Response, error)

func (f funcExec) Execute(ctx context.Context, req executor.Request) (executor.Response, error) {
	return f(ctx, req)
}

type broker struct {
	t                   *testing.T
	url                 string
	ch                  *amqp.Channel
	jobs, dead, replies string
}

func newBroker(t *testing.T) *broker {
	t.Helper()
	url := os.Getenv("RABBITMQ_TEST_URL")
	if url == "" {
		t.Skip("RABBITMQ_TEST_URL not set")
	}
	conn, err := amqp.Dial(url)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { conn.Close() })
	ch, err := conn.Channel()
	if err != nil {
		t.Fatal(err)
	}
	if err := ch.Confirm(false); err != nil {
		t.Fatal(err)
	}
	b := make([]byte, 6)
	_, _ = rand.Read(b)
	prefix := "runner-test." + hex.EncodeToString(b) + "."
	br := &broker{t: t, url: url, ch: ch, jobs: prefix + "judge.jobs", dead: prefix + "judge.jobs.dead", replies: prefix + "judge.events"}
	t.Cleanup(func() {
		for _, q := range []string{br.jobs, br.dead, br.replies} {
			_, _ = ch.QueueDelete(q, false, false, false)
		}
	})
	return br
}

// declare creates the topology of runner.proto under the test's names.
func (b *broker) declare() {
	b.t.Helper()
	quorum := amqp.Table{"x-queue-type": "quorum"}
	for _, q := range []string{b.dead, b.replies} {
		if _, err := b.ch.QueueDeclare(q, true, false, false, false, quorum); err != nil {
			b.t.Fatal(err)
		}
	}
	if _, err := b.ch.QueueDeclare(b.jobs, true, false, false, false, amqp.Table{
		"x-queue-type":              "quorum",
		"x-delivery-limit":          int32(3),
		"x-dead-letter-exchange":    "",
		"x-dead-letter-routing-key": b.dead,
	}); err != nil {
		b.t.Fatal(err)
	}
}

func (b *broker) publish(msg amqp.Publishing) {
	b.t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	dc, err := b.ch.PublishWithDeferredConfirmWithContext(ctx, "", b.jobs, false, false, msg)
	if err != nil {
		b.t.Fatal(err)
	}
	if ok, err := dc.WaitContext(ctx); err != nil || !ok {
		b.t.Fatalf("publish not confirmed: %v", err)
	}
}

func (b *broker) publishJob(j *ojv1.ExecuteJob, correlationID string) {
	b.t.Helper()
	body, err := proto.Marshal(j)
	if err != nil {
		b.t.Fatal(err)
	}
	b.publish(amqp.Publishing{
		ContentType: ContentType, Type: TypeJob, DeliveryMode: amqp.Persistent,
		ReplyTo: b.replies, CorrelationId: correlationID, Body: body,
	})
}

// get polls queue q for one message.
func (b *broker) get(q string, timeout time.Duration) amqp.Delivery {
	b.t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		d, ok, err := b.ch.Get(q, true)
		if err != nil {
			b.t.Fatal(err)
		}
		if ok {
			return d
		}
		time.Sleep(20 * time.Millisecond)
	}
	b.t.Fatalf("no message on %s within %s", q, timeout)
	return amqp.Delivery{}
}

func (b *broker) event(timeout time.Duration) (*ojv1.JobEvent, amqp.Delivery) {
	b.t.Helper()
	d := b.get(b.replies, timeout)
	ev := &ojv1.JobEvent{}
	if err := proto.Unmarshal(d.Body, ev); err != nil {
		b.t.Fatal(err)
	}
	return ev, d
}

func (b *broker) messages(q string) int {
	b.t.Helper()
	qi, err := b.ch.QueueDeclarePassive(q, true, false, false, false, nil)
	if err != nil {
		b.t.Fatal(err)
	}
	return qi.Messages
}

// start runs a consumer until the returned stop function is called.
func (b *broker) start(ex Executor, cfg Config) (stop func()) {
	b.t.Helper()
	cfg.URL, cfg.Queue, cfg.RunnerID = b.url, b.jobs, "itest"
	cfg.MinBackoff, cfg.MaxBackoff = 50*time.Millisecond, 200*time.Millisecond
	if cfg.Workers == 0 {
		cfg.Workers = 2
	}
	c := New(cfg, &Handler{Exec: ex, RunnerID: "itest", Log: quietLog()})
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- c.Run(ctx) }()
	var stopped bool
	stop = func() {
		if stopped {
			return
		}
		stopped = true
		cancel()
		select {
		case err := <-done:
			if err != nil {
				b.t.Errorf("Run: %v", err)
			}
		case <-time.After(30 * time.Second):
			b.t.Fatal("consumer did not stop")
		}
	}
	b.t.Cleanup(stop)
	return stop
}

func echoExec() Executor {
	return funcExec(func(_ context.Context, req executor.Request) (executor.Response, error) {
		resp := executor.Response{Status: executor.StatusOK}
		for _, tc := range req.Tests {
			resp.Results = append(resp.Results, executor.TestResult{ID: tc.ID, Status: executor.StatusOK, Stdout: tc.Stdin})
		}
		return resp, nil
	})
}

func TestIntegrationJobRoundTrip(t *testing.T) {
	b := newBroker(t)
	health := filepath.Join(t.TempDir(), "healthy")
	// Start before the queue exists: the consumer must keep retrying.
	stop := b.start(echoExec(), Config{HealthFile: health})
	time.Sleep(200 * time.Millisecond)
	b.declare()

	b.publishJob(&ojv1.ExecuteJob{
		JobId: "submission-42", SubmissionId: 42, Language: ojv1.Language_LANGUAGE_PYTHON,
		Source: "print(input())", Tests: []*ojv1.TestInput{{Id: "1", Stdin: "hi\n"}},
	}, "corr-42")

	started, d1 := b.event(15 * time.Second)
	finished, d2 := b.event(5 * time.Second)
	if started.GetStarted() == nil || finished.GetFinished() == nil {
		t.Fatalf("want started then finished, got %v then %v", started, finished)
	}
	for _, d := range []amqp.Delivery{d1, d2} {
		if d.CorrelationId != "corr-42" || d.ContentType != ContentType || d.Type != TypeJobEvent || d.DeliveryMode != amqp.Persistent {
			t.Fatalf("bad event properties %+v", d)
		}
	}
	f := finished.GetFinished()
	if finished.GetJobId() != "submission-42" || finished.GetSubmissionId() != 42 || finished.GetRunnerId() != "itest" ||
		f.GetStatus() != ojv1.ExecuteStatus_EXECUTE_STATUS_OK || f.GetResults()[0].GetStdout() != "hi\n" {
		t.Fatalf("bad finished event %v", finished)
	}
	if err := CheckHealth(health, 20*time.Second); err != nil {
		t.Fatalf("heartbeat missing while consuming: %v", err)
	}

	stop()
	// Acked: nothing is left (an unacked job would be back after the close).
	time.Sleep(100 * time.Millisecond)
	if n := b.messages(b.jobs); n != 0 {
		t.Fatalf("%d job(s) left on the queue after ack", n)
	}
}

func TestIntegrationBadMessageIsDeadLettered(t *testing.T) {
	b := newBroker(t)
	b.declare()
	b.start(echoExec(), Config{})

	b.publish(amqp.Publishing{Type: "oj.v1.Bogus", ReplyTo: b.replies, Body: []byte("x")})
	if d := b.get(b.dead, 10*time.Second); d.Type != "oj.v1.Bogus" {
		t.Fatalf("unexpected dead letter %+v", d)
	}
	if n := b.messages(b.replies); n != 0 {
		t.Fatalf("no event expected for a bad message, got %d", n)
	}
}

// The runner counts attempts itself (x-acquired-count): RabbitMQ 4 does not
// count explicit requeues against x-delivery-limit.
func TestIntegrationCrashLoopIsDeadLettered(t *testing.T) {
	b := newBroker(t)
	b.declare()
	b.start(funcExec(func(context.Context, executor.Request) (executor.Response, error) {
		return executor.Response{}, errors.New("infrastructure failure")
	}), Config{})

	b.publishJob(&ojv1.ExecuteJob{JobId: "crash", Language: ojv1.Language_LANGUAGE_C, Source: "x",
		Tests: []*ojv1.TestInput{{Id: "1"}}}, "corr-crash")
	d := b.get(b.dead, 20*time.Second)
	j := &ojv1.ExecuteJob{}
	if err := proto.Unmarshal(d.Body, j); err != nil || j.GetJobId() != "crash" {
		t.Fatalf("unexpected dead letter %+v (%v)", d, err)
	}
}

func TestIntegrationGracefulShutdownFinishesInFlightJob(t *testing.T) {
	b := newBroker(t)
	b.declare()
	release := make(chan struct{})
	stop := b.start(funcExec(func(ctx context.Context, req executor.Request) (executor.Response, error) {
		select {
		case <-release:
		case <-ctx.Done():
			return executor.Response{}, ctx.Err()
		}
		return echoExec().Execute(ctx, req)
	}), Config{ShutdownTimeout: 10 * time.Second})

	b.publishJob(&ojv1.ExecuteJob{JobId: "slow", Language: ojv1.Language_LANGUAGE_C, Source: "x",
		Tests: []*ojv1.TestInput{{Id: "1", Stdin: "ok"}}}, "corr-slow")
	if ev, _ := b.event(10 * time.Second); ev.GetStarted() == nil {
		t.Fatalf("want started, got %v", ev)
	}

	stopped := make(chan struct{})
	go func() { stop(); close(stopped) }()
	time.Sleep(300 * time.Millisecond) // shutdown has begun; the job is still running
	select {
	case <-stopped:
		t.Fatal("Run returned before the in-flight job finished")
	default:
	}
	// A job published now must not be taken by the stopping consumer.
	b.publishJob(&ojv1.ExecuteJob{JobId: "late", Language: ojv1.Language_LANGUAGE_C, Source: "x",
		Tests: []*ojv1.TestInput{{Id: "1"}}}, "corr-late")
	close(release)
	<-stopped

	ev, _ := b.event(5 * time.Second)
	if ev.GetJobId() != "slow" || ev.GetFinished().GetStatus() != ojv1.ExecuteStatus_EXECUTE_STATUS_OK {
		t.Fatalf("want finished for the in-flight job, got %v", ev)
	}
	time.Sleep(100 * time.Millisecond)
	if n := b.messages(b.replies); n != 0 {
		t.Fatalf("the late job must not have been started, %d extra event(s)", n)
	}
	if n := b.messages(b.jobs); n != 1 {
		t.Fatalf("want only the late job left on the queue, got %d", n)
	}
}

func TestIntegrationShutdownTimeoutRequeuesJob(t *testing.T) {
	b := newBroker(t)
	b.declare()
	stop := b.start(funcExec(func(ctx context.Context, _ executor.Request) (executor.Response, error) {
		<-ctx.Done()
		return executor.Response{}, ctx.Err()
	}), Config{ShutdownTimeout: 300 * time.Millisecond})

	b.publishJob(&ojv1.ExecuteJob{JobId: "stuck", Language: ojv1.Language_LANGUAGE_C, Source: "x",
		Tests: []*ojv1.TestInput{{Id: "1"}}}, "corr-stuck")
	if ev, _ := b.event(10 * time.Second); ev.GetStarted() == nil {
		t.Fatalf("want started, got %v", ev)
	}
	stop()
	time.Sleep(100 * time.Millisecond)
	if n := b.messages(b.jobs); n != 1 {
		t.Fatalf("aborted job must be back on the queue, got %d", n)
	}
}

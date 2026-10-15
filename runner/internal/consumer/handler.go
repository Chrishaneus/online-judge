// Package consumer takes ExecuteJobs from RabbitMQ, runs them with the
// executor and publishes JobEvents back to the job's reply_to queue.
//
// The contract (topology, AMQP properties, ack semantics) is the header of
// proto/oj/v1/runner.proto. In short: publish `started`, execute, publish
// `finished` with publisher confirms, and only then ack the job.
package consumer

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
	"google.golang.org/protobuf/proto"

	"github.com/online-judge/online-judge/runner/internal/executor"
	ojv1 "github.com/online-judge/online-judge/runner/internal/gen/oj/v1"
)

// AMQP properties from runner.proto.
const (
	ContentType  = "application/x-protobuf"
	TypeJob      = "oj.v1.ExecuteJob"
	TypeJobEvent = "oj.v1.JobEvent"
)

// DefaultMaxAttempts matches the x-delivery-limit of judge.jobs.
const DefaultMaxAttempts = 3

// DefaultMaxEventBytes bounds the stdout+stderr carried by one finished
// event, so it stays well below RabbitMQ's default 16 MiB message limit.
const DefaultMaxEventBytes = 8 << 20

// Executor runs one job. *executor.Executor implements it.
type Executor interface {
	Execute(ctx context.Context, req executor.Request) (executor.Response, error)
}

// Publisher publishes msg to the default exchange with the given routing key
// and blocks until the broker has confirmed it.
type Publisher interface {
	Publish(ctx context.Context, routingKey string, msg amqp.Publishing) error
}

// Handler processes single deliveries. It is safe for concurrent use.
type Handler struct {
	Exec     Executor
	Pub      Publisher
	RunnerID string
	MaxEvent int // see DefaultMaxEventBytes; <= 0 uses the default
	// MaxAttempts is how many times a job may hit an infrastructure error
	// before it is dead-lettered; <= 0 uses DefaultMaxAttempts.
	MaxAttempts int
	PubTimeout  time.Duration // per publish (incl. confirm); <= 0 means 30s
	Log         *slog.Logger
}

// Handle processes one delivery and always settles it (ack or nack):
//
//   - not an ExecuteJob (wrong type, undecodable) or no reply_to:
//     nack without requeue, so the broker dead-letters it;
//   - executed, rejected or compile error: `finished` is published and
//     confirmed, then the job is acked;
//   - infrastructure failure (executor error, publish not confirmed):
//     nack with requeue, so another attempt happens, until this was attempt
//     MaxAttempts; then nack without requeue (dead-letter). The runner has to
//     count itself: RabbitMQ 4 quorum queues only count deliveries returned
//     by a closed channel (a crashed runner) against x-delivery-limit, not
//     explicit requeues;
//   - ctx cancelled (shutdown timeout, lost connection): nack with requeue,
//     the job is not at fault.
func (h *Handler) Handle(ctx context.Context, d amqp.Delivery) {
	log := h.logger().With("delivery_tag", d.DeliveryTag, "correlation_id", d.CorrelationId, "redelivered", d.Redelivered)

	if d.Type != TypeJob {
		log.Error("dropping message with unexpected type", "type", d.Type)
		nack(log, d, false)
		return
	}
	job := &ojv1.ExecuteJob{}
	if err := proto.Unmarshal(d.Body, job); err != nil {
		log.Error("dropping undecodable job", "err", err)
		nack(log, d, false)
		return
	}
	log = log.With("job_id", job.GetJobId(), "submission_id", job.GetSubmissionId())
	if d.ReplyTo == "" {
		log.Error("dropping job without reply_to")
		nack(log, d, false)
		return
	}

	if err := h.publish(ctx, d, h.started(job)); err != nil {
		h.retry(ctx, log, d, fmt.Errorf("publish started event: %w", err))
		return
	}

	start := time.Now()
	result, err := h.execute(ctx, job)
	if err != nil {
		h.retry(ctx, log, d, fmt.Errorf("execute: %w", err))
		return
	}
	log = log.With("status", result.GetStatus().String(), "tests", len(result.GetResults()), "duration_ms", time.Since(start).Milliseconds())

	if err := h.publish(ctx, d, h.finished(job, result)); err != nil {
		h.retry(ctx, log, d, fmt.Errorf("publish finished event: %w", err))
		return
	}
	if err := d.Ack(false); err != nil {
		// The channel is gone: the job is redelivered and executed again,
		// which the midlayer tolerates (at-least-once).
		log.Error("ack failed", "err", err)
		return
	}
	log.Info("job done")
}

// execute runs job. A non-nil error means an infrastructure failure; every
// problem with the job itself is reported in the result.
func (h *Handler) execute(ctx context.Context, job *ojv1.ExecuteJob) (*ojv1.ExecuteResult, error) {
	langID, ok := LanguageID(job.GetLanguage())
	if !ok {
		return rejected(fmt.Sprintf("unsupported language %s", job.GetLanguage())), nil
	}
	req := executor.Request{
		Language:      langID,
		Source:        job.GetSource(),
		Tests:         make([]executor.TestInput, len(job.GetTests())),
		TimeLimitMs:   int(job.GetTimeLimitMs()),
		MemoryLimitMB: int(job.GetMemoryLimitMb()),
	}
	for i, t := range job.GetTests() {
		req.Tests[i] = executor.TestInput{ID: t.GetId(), Stdin: t.GetStdin()}
	}
	resp, err := h.Exec.Execute(ctx, req)
	var ve *executor.ValidationError
	if errors.As(err, &ve) {
		return rejected(ve.Msg), nil
	}
	if err != nil {
		return nil, err
	}
	return ToResult(resp, h.maxEvent())
}

func (h *Handler) started(job *ojv1.ExecuteJob) *ojv1.JobEvent {
	ev := h.event(job)
	ev.Event = &ojv1.JobEvent_Started{Started: &ojv1.JobStarted{}}
	return ev
}

func (h *Handler) finished(job *ojv1.ExecuteJob, r *ojv1.ExecuteResult) *ojv1.JobEvent {
	ev := h.event(job)
	ev.Event = &ojv1.JobEvent_Finished{Finished: r}
	return ev
}

func (h *Handler) event(job *ojv1.ExecuteJob) *ojv1.JobEvent {
	return &ojv1.JobEvent{JobId: job.GetJobId(), SubmissionId: job.GetSubmissionId(), RunnerId: h.RunnerID}
}

// publish sends ev to the job's reply_to with the properties required by
// runner.proto and waits for the broker's confirm.
func (h *Handler) publish(ctx context.Context, d amqp.Delivery, ev *ojv1.JobEvent) error {
	body, err := proto.Marshal(ev)
	if err != nil {
		return fmt.Errorf("marshal event: %w", err)
	}
	timeout := h.PubTimeout
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	return h.Pub.Publish(ctx, d.ReplyTo, amqp.Publishing{
		ContentType:   ContentType,
		Type:          TypeJobEvent,
		DeliveryMode:  amqp.Persistent,
		CorrelationId: d.CorrelationId,
		AppId:         "runner",
		Timestamp:     time.Now(),
		Body:          body,
	})
}

func (h *Handler) logger() *slog.Logger {
	if h.Log != nil {
		return h.Log
	}
	return slog.Default()
}

func (h *Handler) maxEvent() int {
	if h.MaxEvent > 0 {
		return h.MaxEvent
	}
	return DefaultMaxEventBytes
}

// retry settles a job that failed for a reason unrelated to the job.
func (h *Handler) retry(ctx context.Context, log *slog.Logger, d amqp.Delivery, err error) {
	if ctx.Err() != nil {
		log.Warn("job aborted; requeueing", "err", err)
		nack(log, d, true)
		return
	}
	limit := h.MaxAttempts
	if limit <= 0 {
		limit = DefaultMaxAttempts
	}
	if n := Attempt(d); n >= limit {
		log.Error("job failed on its last attempt; dead-lettering", "attempt", n, "err", err)
		nack(log, d, false)
		return
	}
	log.Error("job failed; requeueing", "attempt", Attempt(d), "err", err)
	nack(log, d, true)
}

// Attempt returns the 1-based delivery attempt of d, from the quorum queue's
// x-acquired-count / x-delivery-count headers (absent on the first delivery).
func Attempt(d amqp.Delivery) int {
	n := 0
	for _, h := range []string{"x-acquired-count", "x-delivery-count"} {
		if c := headerInt(d.Headers[h]); c > n {
			n = c
		}
	}
	return n + 1
}

func headerInt(v any) int {
	switch v := v.(type) {
	case int8:
		return int(v)
	case int16:
		return int(v)
	case int32:
		return int(v)
	case int64:
		return int(v)
	case int:
		return v
	case uint8:
		return int(v)
	case uint16:
		return int(v)
	case uint32:
		return int(v)
	case uint64:
		return int(v)
	}
	return 0
}

func nack(log *slog.Logger, d amqp.Delivery, requeue bool) {
	if err := d.Nack(false, requeue); err != nil {
		log.Error("nack failed", "requeue", requeue, "err", err)
	}
}

func rejected(msg string) *ojv1.ExecuteResult {
	return &ojv1.ExecuteResult{Status: ojv1.ExecuteStatus_EXECUTE_STATUS_REJECTED, Error: msg}
}

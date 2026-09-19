package consumer

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
)

// Config configures a Consumer.
type Config struct {
	URL      string // amqp://user:pass@host:5672/vhost
	Queue    string // queue to consume ExecuteJobs from (judge.jobs)
	Workers  int    // prefetch and maximum concurrent jobs
	RunnerID string // used in the connection name and consumer tag

	// ShutdownTimeout bounds how long Run waits for in-flight jobs after ctx
	// is cancelled. Jobs still running after it are aborted and, being
	// unacked, redelivered by the broker.
	ShutdownTimeout time.Duration

	// HealthFile is touched every HealthInterval while consuming; empty
	// disables the heartbeat.
	HealthFile     string
	HealthInterval time.Duration

	// Reconnect backoff: starts at MinBackoff, doubles up to MaxBackoff.
	MinBackoff time.Duration
	MaxBackoff time.Duration
}

// Consumer consumes jobs with reconnects and graceful shutdown.
type Consumer struct {
	cfg     Config
	handler *Handler
	log     *slog.Logger
}

// New returns a consumer that hands each delivery to h. h.Pub is replaced
// with a publisher on the consumer's own connection.
func New(cfg Config, h *Handler) *Consumer {
	if cfg.Queue == "" {
		cfg.Queue = "judge.jobs"
	}
	if cfg.Workers <= 0 {
		cfg.Workers = 1
	}
	if cfg.ShutdownTimeout <= 0 {
		cfg.ShutdownTimeout = 60 * time.Second
	}
	if cfg.HealthInterval <= 0 {
		cfg.HealthInterval = 5 * time.Second
	}
	if cfg.MinBackoff <= 0 {
		cfg.MinBackoff = 500 * time.Millisecond
	}
	if cfg.MaxBackoff <= 0 {
		cfg.MaxBackoff = 30 * time.Second
	}
	return &Consumer{cfg: cfg, handler: h, log: h.logger()}
}

// Run consumes until ctx is cancelled, reconnecting with backoff whenever
// the broker is unreachable, the queue does not exist yet, or the connection
// is lost. It returns nil after a graceful shutdown.
func (c *Consumer) Run(ctx context.Context) error {
	backoff := c.cfg.MinBackoff
	for {
		consumed, err := c.session(ctx)
		if ctx.Err() != nil {
			return nil
		}
		if consumed {
			backoff = c.cfg.MinBackoff
		}
		c.log.Warn("broker session ended; reconnecting", "err", err, "in", backoff)
		select {
		case <-ctx.Done():
			return nil
		case <-time.After(backoff):
		}
		backoff = min(2*backoff, c.cfg.MaxBackoff)
	}
}

// session runs one connection. consumed reports whether it got as far as
// consuming (used to reset the backoff).
func (c *Consumer) session(ctx context.Context) (consumed bool, err error) {
	props := amqp.NewConnectionProperties()
	props.SetClientConnectionName("oj-runner " + c.cfg.RunnerID)
	conn, err := amqp.DialConfig(c.cfg.URL, amqp.Config{
		Heartbeat:  10 * time.Second,
		Properties: props,
	})
	if err != nil {
		return false, fmt.Errorf("dial: %w", redact(err, c.cfg.URL))
	}
	defer conn.Close()
	connClosed := conn.NotifyClose(make(chan *amqp.Error, 1))

	pubCh, err := conn.Channel()
	if err != nil {
		return false, fmt.Errorf("open publish channel: %w", err)
	}
	if err := pubCh.Confirm(false); err != nil {
		return false, fmt.Errorf("enable publisher confirms: %w", err)
	}
	conCh, err := conn.Channel()
	if err != nil {
		return false, fmt.Errorf("open consume channel: %w", err)
	}
	conChClosed := conCh.NotifyClose(make(chan *amqp.Error, 1))
	pubChClosed := pubCh.NotifyClose(make(chan *amqp.Error, 1))
	if err := conCh.Qos(c.cfg.Workers, 0, false); err != nil {
		return false, fmt.Errorf("set prefetch: %w", err)
	}
	tag := fmt.Sprintf("oj-runner-%s-%d", c.cfg.RunnerID, time.Now().UnixNano())
	// The queue is not declared here: the runner's broker user has no
	// configure permission, the topology comes from the broker definitions.
	deliveries, err := conCh.Consume(c.cfg.Queue, tag, false, false, false, false, nil)
	if err != nil {
		return false, fmt.Errorf("consume %q: %w", c.cfg.Queue, err)
	}
	c.log.Info("consuming", "queue", c.cfg.Queue, "prefetch", c.cfg.Workers, "consumer_tag", tag)

	h := *c.handler
	h.Pub = &channelPublisher{ch: pubCh}

	// Jobs run on their own context: a shutdown signal must not abort them,
	// only stop new ones from being taken.
	jobCtx, cancelJobs := context.WithCancel(context.WithoutCancel(ctx))
	defer cancelJobs()
	var inflight sync.WaitGroup
	defer inflight.Wait()

	c.touchHealth()
	health := time.NewTicker(c.cfg.HealthInterval)
	defer health.Stop()

	for {
		select {
		case <-health.C:
			c.touchHealth()
		case d, ok := <-deliveries:
			if !ok {
				cancelJobs() // their acks can no longer succeed
				return true, errors.New("delivery channel closed")
			}
			inflight.Add(1)
			go func() {
				defer inflight.Done()
				h.Handle(jobCtx, d)
			}()
		case e := <-connClosed:
			cancelJobs()
			return true, fmt.Errorf("connection closed: %v", e)
		case e := <-conChClosed:
			cancelJobs()
			return true, fmt.Errorf("consume channel closed: %v", e)
		case e := <-pubChClosed:
			cancelJobs()
			return true, fmt.Errorf("publish channel closed: %v", e)
		case <-ctx.Done():
			c.shutdown(conCh, tag, &inflight, cancelJobs)
			return true, nil
		}
	}
}

// shutdown stops taking jobs and waits (bounded) for in-flight ones.
// Deliveries already prefetched but not started stay unacked and are
// redelivered when the connection closes.
func (c *Consumer) shutdown(ch *amqp.Channel, tag string, inflight *sync.WaitGroup, cancelJobs context.CancelFunc) {
	c.log.Info("shutting down: no new jobs, waiting for in-flight ones", "timeout", c.cfg.ShutdownTimeout)
	if err := ch.Cancel(tag, false); err != nil {
		c.log.Warn("cancel consumer", "err", err)
	}
	done := make(chan struct{})
	go func() { inflight.Wait(); close(done) }()
	select {
	case <-done:
		c.log.Info("in-flight jobs finished")
	case <-time.After(c.cfg.ShutdownTimeout):
		c.log.Warn("shutdown timeout: aborting in-flight jobs, the broker will redeliver them")
		cancelJobs()
	}
}

// channelPublisher publishes on a channel in confirm mode.
type channelPublisher struct{ ch *amqp.Channel }

func (p *channelPublisher) Publish(ctx context.Context, routingKey string, msg amqp.Publishing) error {
	dc, err := p.ch.PublishWithDeferredConfirmWithContext(ctx, "", routingKey, false, false, msg)
	if err != nil {
		return err
	}
	acked, err := dc.WaitContext(ctx)
	if err != nil {
		return fmt.Errorf("wait for confirm: %w", err)
	}
	if !acked {
		return errors.New("broker nacked the publish")
	}
	return nil
}

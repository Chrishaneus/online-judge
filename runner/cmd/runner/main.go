// Command runner is the online judge code execution worker. It consumes
// oj.v1.ExecuteJob messages from RabbitMQ, runs them in the sandbox and
// publishes oj.v1.JobEvent messages back (see oj-proto/oj/v1/runner.proto).
//
// Usage:
//
//	runner              consume jobs until SIGTERM/SIGINT
//	runner healthcheck  exit 0 iff the heartbeat file is fresh
package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"syscall"
	"time"

	"github.com/online-judge/oj-runner/internal/consumer"
	"github.com/online-judge/oj-runner/internal/executor"
)

// healthMaxAge is how old the heartbeat (written every 5s) may get.
const healthMaxAge = 20 * time.Second

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	healthFile := envOr("RUNNER_HEALTH_FILE", "/tmp/runner-healthy")

	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		if err := consumer.CheckHealth(healthFile, healthMaxAge); err != nil {
			fmt.Fprintln(os.Stderr, "unhealthy:", err)
			os.Exit(1)
		}
		return
	}
	if err := run(healthFile); err != nil {
		slog.Error("fatal", "err", err)
		os.Exit(1)
	}
}

func run(healthFile string) error {
	// The broker URL carries credentials. Take it out of the environment
	// before anything else runs; sandboxed processes additionally get an
	// explicit minimal environment (see internal/sandbox).
	amqpURL := envOr("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
	if err := os.Unsetenv("RABBITMQ_URL"); err != nil {
		return err
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	useCreds := os.Geteuid() == 0 && os.Getenv("RUNNER_DISABLE_SETUID") != "1"
	if !useCreds {
		slog.Warn("not running as root: sandboxed code runs as the service user (dev mode)")
	}
	ex, err := executor.New(executor.Config{
		SandboxRoot:    envOr("RUNNER_SANDBOX_DIR", filepath.Join(os.TempDir(), "oj-sandbox")),
		Workers:        envInt("RUNNER_WORKERS", 2),
		UIDBase:        envInt("RUNNER_UID_BASE", 20000),
		UseCredentials: useCreds,
		MaxOutputBytes: envInt("RUNNER_MAX_OUTPUT_BYTES", 1<<20),
	})
	if err != nil {
		return err
	}

	runnerID := os.Getenv("RUNNER_ID")
	if runnerID == "" {
		runnerID, _ = os.Hostname()
	}
	queue := envOr("RUNNER_QUEUE", "judge.jobs")
	slog.Info("runner starting", "runner_id", runnerID, "queue", queue, "workers", ex.Workers(), "setuid", useCreds)

	c := consumer.New(consumer.Config{
		URL:             amqpURL,
		Queue:           queue,
		Workers:         ex.Workers(),
		RunnerID:        runnerID,
		ShutdownTimeout: time.Duration(envInt("RUNNER_SHUTDOWN_TIMEOUT_S", 60)) * time.Second,
		HealthFile:      healthFile,
	}, &consumer.Handler{Exec: ex, RunnerID: runnerID, MaxEvent: envInt("RUNNER_MAX_EVENT_BYTES", consumer.DefaultMaxEventBytes)})
	err = c.Run(ctx)
	slog.Info("runner stopped")
	return err
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
		slog.Warn("ignoring invalid integer env var", "key", key, "value", v)
	}
	return def
}

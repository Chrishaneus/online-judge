// Command rest runs the public REST API gateway of the online judge.
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"github.com/online-judge/online-judge/rest/internal/gateway"
	ojv1 "github.com/online-judge/online-judge/rest/internal/gen/oj/v1"
)

// maxMsgSize allows admin uploads of large test cases (see MaxBody limits).
const maxMsgSize = 64 << 20

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		os.Exit(healthcheck(envOr("REST_ADDR", ":8000")))
	}
	if err := run(); err != nil {
		slog.Error("fatal", "err", err)
		os.Exit(1)
	}
}

func run() error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// The midlayer is on the internal network: plaintext gRPC. NewClient
	// connects lazily and reconnects on its own.
	upstream := envOr("MIDLAYER_ADDR", "localhost:50051")
	conn, err := grpc.NewClient(upstream,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithDefaultCallOptions(
			grpc.MaxCallRecvMsgSize(maxMsgSize),
			grpc.MaxCallSendMsgSize(maxMsgSize),
		),
	)
	if err != nil {
		return fmt.Errorf("midlayer client %q: %w", upstream, err)
	}
	defer conn.Close()

	token := os.Getenv("ADMIN_TOKEN")
	if token == "" {
		slog.Warn("ADMIN_TOKEN not set: admin API disabled")
	} else if len(token) < 16 {
		slog.Warn("ADMIN_TOKEN is short; use at least 16 random characters")
	}

	cfg := gateway.Config{
		Client:          ojv1.NewJudgeServiceClient(conn),
		AdminToken:      token,
		CORSOrigins:     strings.Split(envOr("CORS_ORIGINS", "*"), ","),
		RateLimitPerMin: envInt("RATE_LIMIT_PER_MIN", 20),
		RateLimitBurst:  envInt("RATE_LIMIT_BURST", 5),
		TrustProxy:      os.Getenv("TRUST_PROXY_HEADERS") == "true",
		UpstreamTimeout: time.Duration(envInt("UPSTREAM_TIMEOUT_S", 60)) * time.Second,
		RunTimeout:      time.Duration(envInt("RUN_TIMEOUT_S", 60)) * time.Second,
	}
	addr := envOr("REST_ADDR", ":8000")
	srv := &http.Server{
		Addr:              addr,
		Handler:           gateway.New(cfg),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       60 * time.Second,
		WriteTimeout:      max(cfg.UpstreamTimeout, cfg.RunTimeout) + 10*time.Second,
		IdleTimeout:       120 * time.Second,
	}

	errCh := make(chan error, 1)
	go func() {
		slog.Info("rest gateway listening", "addr", addr, "midlayer", upstream)
		errCh <- srv.ListenAndServe()
	}()
	select {
	case err := <-errCh:
		if !errors.Is(err, http.ErrServerClosed) {
			return err
		}
	case <-ctx.Done():
		slog.Info("shutting down")
	}
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	return srv.Shutdown(shutdownCtx)
}

func healthcheck(addr string) int {
	if strings.HasPrefix(addr, ":") {
		addr = "127.0.0.1" + addr
	}
	c := &http.Client{Timeout: 3 * time.Second}
	resp, err := c.Get("http://" + addr + "/healthz")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return 1
	}
	return 0
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
		slog.Warn("ignoring invalid integer env var", "key", key)
	}
	return def
}

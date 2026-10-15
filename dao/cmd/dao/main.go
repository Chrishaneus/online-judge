// Command dao runs the online judge persistence service: a gRPC server
// implementing oj.v1.DaoService plus grpc.health.v1.Health.
//
// Usage:
//
//	dao               serve (default)
//	dao healthcheck   exit 0 iff the server at DAO_ADDR reports SERVING
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/online-judge/online-judge/dao/internal/grpcapi"
	"github.com/online-judge/online-judge/dao/internal/store"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
)

const (
	defaultAddr     = ":50052"
	healthInterval  = 5 * time.Second
	shutdownTimeout = 10 * time.Second
)

func main() {
	if len(os.Args) > 1 {
		switch os.Args[1] {
		case "healthcheck":
			if err := healthcheck(envOr("DAO_ADDR", defaultAddr)); err != nil {
				fmt.Fprintln(os.Stderr, "unhealthy:", err)
				os.Exit(1)
			}
			return
		case "serve":
		default:
			fmt.Fprintf(os.Stderr, "usage: %s [serve|healthcheck]\n", os.Args[0])
			os.Exit(2)
		}
	}
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	if err := run(); err != nil {
		slog.Error("fatal", "err", err)
		os.Exit(1)
	}
}

func run() error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	addr := envOr("DAO_ADDR", defaultAddr)

	var st store.Store
	if dsn := os.Getenv("DATABASE_URL"); dsn != "" {
		connectCtx, cancel := context.WithTimeout(ctx, 60*time.Second)
		pg, err := store.NewPostgres(connectCtx, dsn)
		cancel()
		if err != nil {
			return err
		}
		defer pg.Close()
		if err := pg.Migrate(ctx); err != nil {
			return err
		}
		st = pg
		slog.Info("using postgres store")
	} else {
		slog.Warn("DATABASE_URL not set; using in-memory store (data is not persisted)")
		st = store.NewMemory()
	}

	lis, err := net.Listen("tcp", addr)
	if err != nil {
		return err
	}
	hs := health.NewServer()
	srv := grpcapi.NewGRPCServer(st, hs)

	healthCtx, stopHealth := context.WithCancel(ctx)
	defer stopHealth()
	checker := grpcapi.NewHealthChecker(st, hs, healthInterval)
	checker.CheckOnce(healthCtx)
	go checker.Run(healthCtx)

	errCh := make(chan error, 1)
	go func() {
		slog.Info("dao listening", "addr", lis.Addr().String())
		errCh <- srv.Serve(lis)
	}()

	select {
	case err := <-errCh:
		return err
	case <-ctx.Done():
		slog.Info("shutting down")
	}
	stopHealth()
	hs.Shutdown() // report NOT_SERVING to watchers while draining
	done := make(chan struct{})
	go func() {
		srv.GracefulStop()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(shutdownTimeout):
		slog.Warn("graceful stop timed out; forcing")
		srv.Stop()
	}
	if err := <-errCh; err != nil && !errors.Is(err, grpc.ErrServerStopped) {
		return err
	}
	return nil
}

// healthcheck calls grpc.health.v1.Health/Check on the local server and
// returns nil iff it reports SERVING.
func healthcheck(addr string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	conn, err := grpc.NewClient(dialTarget(addr), grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return err
	}
	defer conn.Close()
	resp, err := healthpb.NewHealthClient(conn).Check(ctx, &healthpb.HealthCheckRequest{})
	if err != nil {
		return err
	}
	if resp.GetStatus() != healthpb.HealthCheckResponse_SERVING {
		return fmt.Errorf("status %s", resp.GetStatus())
	}
	return nil
}

// dialTarget turns a listen address (":50052", "0.0.0.0:50052") into a
// loopback address the client can dial.
func dialTarget(addr string) string {
	host, port, err := net.SplitHostPort(addr)
	if err != nil {
		return addr
	}
	switch host {
	case "", "0.0.0.0", "::":
		host = "127.0.0.1"
	}
	return "passthrough:///" + net.JoinHostPort(host, port)
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

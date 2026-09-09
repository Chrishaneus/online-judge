// Command dao runs the online judge repository (data access) service.
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/online-judge/oj-dao/internal/api"
	"github.com/online-judge/oj-dao/internal/store"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	if err := run(); err != nil {
		slog.Error("fatal", "err", err)
		os.Exit(1)
	}
}

func run() error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	addr := envOr("DAO_ADDR", ":8001")

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

	srv := &http.Server{
		Addr:              addr,
		Handler:           api.New(st),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      30 * time.Second,
	}

	errCh := make(chan error, 1)
	go func() {
		slog.Info("dao listening", "addr", addr)
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
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	return srv.Shutdown(shutdownCtx)
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

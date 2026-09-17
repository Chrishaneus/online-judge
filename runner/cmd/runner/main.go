// Command runner is the online judge code execution service.
//
// Usage:
//
//	runner              serve the API on $RUNNER_ADDR
//	runner healthcheck  probe $RUNNER_ADDR/healthz (exit 0 when healthy)
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/online-judge/oj-runner/internal/api"
	"github.com/online-judge/oj-runner/internal/executor"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	addr := envOr("RUNNER_ADDR", ":8002")

	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		if err := healthcheck(addr); err != nil {
			fmt.Fprintln(os.Stderr, "unhealthy:", err)
			os.Exit(1)
		}
		return
	}
	if err := run(addr); err != nil {
		slog.Error("fatal", "err", err)
		os.Exit(1)
	}
}

func run(addr string) error {
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

	ln, err := listen(addr, envInt("RUNNER_SOCKET_GID", -1))
	if err != nil {
		return err
	}
	srv := &http.Server{
		Handler:           api.New(ex),
		ReadHeaderTimeout: 5 * time.Second,
		// Batches can legitimately take minutes (many tests x time limit).
		WriteTimeout: 15 * time.Minute,
	}
	errCh := make(chan error, 1)
	go func() {
		slog.Info("runner listening", "addr", addr, "workers", ex.Workers(), "setuid", useCreds)
		errCh <- srv.Serve(ln)
	}()

	select {
	case err := <-errCh:
		if !errors.Is(err, http.ErrServerClosed) {
			return err
		}
	case <-ctx.Done():
		slog.Info("shutting down")
	}
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	return srv.Shutdown(shutdownCtx)
}

// listen supports "host:port" and "unix:///path/to.sock". For unix sockets the
// socket (and its directory) are restricted to root and the given group.
func listen(addr string, gid int) (net.Listener, error) {
	path, isUnix := strings.CutPrefix(addr, "unix://")
	if !isUnix {
		return net.Listen("tcp", addr)
	}
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o750); err != nil {
		return nil, err
	}
	_ = os.Remove(path)
	ln, err := net.Listen("unix", path)
	if err != nil {
		return nil, err
	}
	if gid >= 0 {
		for _, p := range []string{dir, path} {
			if err := os.Chown(p, 0, gid); err != nil {
				ln.Close()
				return nil, fmt.Errorf("chown %s: %w", p, err)
			}
		}
	}
	if err := os.Chmod(dir, 0o750); err != nil {
		ln.Close()
		return nil, err
	}
	if err := os.Chmod(path, 0o660); err != nil {
		ln.Close()
		return nil, err
	}
	return ln, nil
}

func healthcheck(addr string) error {
	client := &http.Client{Timeout: 3 * time.Second}
	url := "http://" + addr + "/healthz"
	if path, ok := strings.CutPrefix(addr, "unix://"); ok {
		client.Transport = &http.Transport{
			DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
				var d net.Dialer
				return d.DialContext(ctx, "unix", path)
			},
		}
		url = "http://runner/healthz"
	} else if strings.HasPrefix(addr, ":") {
		url = "http://127.0.0.1" + addr + "/healthz"
	}
	resp, err := client.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("status %d", resp.StatusCode)
	}
	return nil
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

package grpcapi

import (
	"context"
	"log/slog"
	"time"

	ojv1 "github.com/online-judge/online-judge/dao/internal/gen/oj/v1"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
)

// HealthServices are the names whose health status reflects the database:
// "" (the whole server) and the DaoService itself.
var HealthServices = []string{"", ojv1.DaoService_ServiceDesc.ServiceName}

// Pinger is the part of store.Store the health checker needs.
type Pinger interface {
	Ping(ctx context.Context) error
}

// HealthChecker pings the database periodically and publishes the result on
// a standard health server, so Check and Watch both reflect DB reachability.
type HealthChecker struct {
	db       Pinger
	hs       *health.Server
	interval time.Duration
	timeout  time.Duration
	serving  *bool
}

// NewHealthChecker returns a checker publishing to hs. Until the first
// check runs every service reports NOT_SERVING.
func NewHealthChecker(db Pinger, hs *health.Server, interval time.Duration) *HealthChecker {
	for _, name := range HealthServices {
		hs.SetServingStatus(name, healthpb.HealthCheckResponse_NOT_SERVING)
	}
	return &HealthChecker{db: db, hs: hs, interval: interval, timeout: 2 * time.Second}
}

// CheckOnce pings the database and updates the published status. It must
// not be called concurrently (Run calls it from a single goroutine).
func (h *HealthChecker) CheckOnce(ctx context.Context) {
	pingCtx, cancel := context.WithTimeout(ctx, h.timeout)
	err := h.db.Ping(pingCtx)
	cancel()
	ok := err == nil
	if h.serving == nil || *h.serving != ok {
		if ok {
			slog.Info("database reachable; health SERVING")
		} else {
			slog.Warn("database unreachable; health NOT_SERVING", "err", err)
		}
	}
	h.serving = &ok
	st := healthpb.HealthCheckResponse_NOT_SERVING
	if ok {
		st = healthpb.HealthCheckResponse_SERVING
	}
	for _, name := range HealthServices {
		h.hs.SetServingStatus(name, st)
	}
}

// Run checks immediately and then every interval until ctx is done.
func (h *HealthChecker) Run(ctx context.Context) {
	h.CheckOnce(ctx)
	t := time.NewTicker(h.interval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			h.CheckOnce(ctx)
		}
	}
}

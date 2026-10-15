package grpcapi

import (
	"context"
	"errors"
	"fmt"
	"sync/atomic"
	"testing"

	"github.com/online-judge/online-judge/dao/internal/store"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/status"
)

func TestRecoveryInterceptor(t *testing.T) {
	info := &grpc.UnaryServerInfo{FullMethod: "/oj.v1.DaoService/GetProblem"}
	_, err := RecoveryInterceptor(context.Background(), nil, info, func(context.Context, any) (any, error) {
		panic("boom")
	})
	if status.Code(err) != codes.Internal {
		t.Fatalf("want Internal, got %v", err)
	}
	resp, err := RecoveryInterceptor(context.Background(), nil, info, func(context.Context, any) (any, error) {
		return "ok", nil
	})
	if err != nil || resp != "ok" {
		t.Fatalf("passthrough: %v %v", resp, err)
	}
}

func TestLoggingInterceptorPassesThrough(t *testing.T) {
	info := &grpc.UnaryServerInfo{FullMethod: "/oj.v1.DaoService/GetProblem"}
	want := status.Error(codes.NotFound, "not found")
	resp, err := LoggingInterceptor(context.Background(), nil, info, func(context.Context, any) (any, error) {
		return "r", want
	})
	if resp != "r" || !errors.Is(err, want) {
		t.Fatalf("got %v %v", resp, err)
	}
}

func TestStoreErrorCodes(t *testing.T) {
	ctx := context.Background()
	cases := map[error]codes.Code{
		store.ErrNotFound: codes.NotFound,
		fmt.Errorf("wrapped: %w", store.ErrNotFound): codes.NotFound,
		store.ErrConflict:     codes.AlreadyExists,
		store.ErrPrecondition: codes.FailedPrecondition,
		fmt.Errorf("%w: dial tcp: refused", store.ErrUnavailable): codes.Unavailable,
		context.Canceled:                             codes.Canceled,
		context.DeadlineExceeded:                     codes.DeadlineExceeded,
		errors.New("syntax error at or near SELECT"): codes.Internal,
	}
	for in, want := range cases {
		err := storeError(ctx, in)
		if status.Code(err) != want {
			t.Errorf("%v -> %v, want %v", in, status.Code(err), want)
		}
	}
	if msg := status.Convert(storeError(ctx, errors.New("secret detail"))).Message(); msg != "internal error" {
		t.Errorf("internal error leaks details: %q", msg)
	}
}

type fakePinger struct{ fail atomic.Bool }

func (f *fakePinger) Ping(context.Context) error {
	if f.fail.Load() {
		return store.ErrUnavailable
	}
	return nil
}

func TestHealthCheckerReflectsDatabase(t *testing.T) {
	ctx := context.Background()
	hs := health.NewServer()
	db := &fakePinger{}
	hc := NewHealthChecker(db, hs, 0)

	check := func(want healthpb.HealthCheckResponse_ServingStatus) {
		t.Helper()
		for _, name := range HealthServices {
			resp, err := hs.Check(ctx, &healthpb.HealthCheckRequest{Service: name})
			if err != nil || resp.GetStatus() != want {
				t.Fatalf("service %q: %v %v, want %v", name, resp.GetStatus(), err, want)
			}
		}
	}
	check(healthpb.HealthCheckResponse_NOT_SERVING) // before the first ping
	hc.CheckOnce(ctx)
	check(healthpb.HealthCheckResponse_SERVING)
	db.fail.Store(true)
	hc.CheckOnce(ctx)
	check(healthpb.HealthCheckResponse_NOT_SERVING)
	db.fail.Store(false)
	hc.CheckOnce(ctx)
	check(healthpb.HealthCheckResponse_SERVING)
}

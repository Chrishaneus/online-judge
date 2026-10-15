package grpcapi

import (
	"context"
	"log/slog"
	"runtime/debug"
	"strings"
	"time"

	ojv1 "github.com/online-judge/online-judge/dao/internal/gen/oj/v1"
	"github.com/online-judge/online-judge/dao/internal/store"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/keepalive"
	"google.golang.org/grpc/status"
)

// MaxMessageSize bounds request and response sizes (test data can be large).
const MaxMessageSize = 64 << 20

// NewGRPCServer builds a gRPC server serving oj.v1.DaoService backed by st
// and the standard grpc.health.v1.Health service backed by hs.
func NewGRPCServer(st store.Store, hs *health.Server) *grpc.Server {
	srv := grpc.NewServer(
		grpc.MaxRecvMsgSize(MaxMessageSize),
		grpc.MaxSendMsgSize(MaxMessageSize),
		// Let clients send keepalive pings (every >= 10s) without being
		// disconnected with "too_many_pings".
		grpc.KeepaliveEnforcementPolicy(keepalive.EnforcementPolicy{
			MinTime:             10 * time.Second,
			PermitWithoutStream: true,
		}),
		grpc.ChainUnaryInterceptor(LoggingInterceptor, RecoveryInterceptor),
	)
	ojv1.RegisterDaoServiceServer(srv, New(st))
	healthpb.RegisterHealthServer(srv, hs)
	return srv
}

// LoggingInterceptor logs every unary call with its method, status code and
// duration. Health checks are logged at debug level.
func LoggingInterceptor(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
	start := time.Now()
	resp, err := handler(ctx, req)
	level := slog.LevelInfo
	if strings.HasPrefix(info.FullMethod, "/grpc.health.v1.Health/") {
		level = slog.LevelDebug
	}
	slog.Log(ctx, level, "rpc",
		"method", info.FullMethod,
		"code", status.Code(err).String(),
		"duration_ms", float64(time.Since(start).Microseconds())/1000)
	return resp, err
}

// RecoveryInterceptor turns a panicking handler into an INTERNAL error and
// logs the stack instead of crashing the process.
func RecoveryInterceptor(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (resp any, err error) {
	defer func() {
		if r := recover(); r != nil {
			slog.ErrorContext(ctx, "panic in handler", "method", info.FullMethod, "panic", r, "stack", string(debug.Stack()))
			resp, err = nil, status.Error(codes.Internal, "internal error")
		}
	}()
	return handler(ctx, req)
}

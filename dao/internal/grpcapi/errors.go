package grpcapi

import (
	"context"
	"errors"
	"fmt"
	"log/slog"

	"github.com/online-judge/online-judge/dao/internal/store"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// storeError maps a store error to a gRPC status as documented in the header
// of oj/v1/dao.proto. Unexpected errors are logged and returned as a generic
// INTERNAL so no database details leak to clients.
func storeError(ctx context.Context, err error) error {
	switch {
	case errors.Is(err, store.ErrNotFound):
		return status.Error(codes.NotFound, "not found")
	case errors.Is(err, store.ErrConflict):
		return status.Error(codes.AlreadyExists, "already exists")
	case errors.Is(err, store.ErrPrecondition):
		return status.Error(codes.FailedPrecondition, "submission status does not match expected_statuses")
	case errors.Is(err, store.ErrUnavailable):
		slog.WarnContext(ctx, "database unavailable", "err", err)
		return status.Error(codes.Unavailable, "database unavailable")
	case errors.Is(err, context.Canceled):
		return status.Error(codes.Canceled, "request canceled")
	case errors.Is(err, context.DeadlineExceeded):
		return status.Error(codes.DeadlineExceeded, "deadline exceeded")
	default:
		slog.ErrorContext(ctx, "store error", "err", err)
		return status.Error(codes.Internal, "internal error")
	}
}

func invalidArgf(format string, args ...any) error {
	return status.Error(codes.InvalidArgument, fmt.Sprintf(format, args...))
}

package gateway

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"regexp"
	"strconv"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"

	ojv1 "github.com/online-judge/oj-rest/internal/gen/oj/v1"
)

// Canonical proto JSON: camelCase names, enums by name, int64 as strings and
// every field present so clients never have to guess defaults.
var (
	marshal   = protojson.MarshalOptions{EmitUnpopulated: true}
	unmarshal = protojson.UnmarshalOptions{} // rejects unknown fields
)

// rpc returns a handler that builds the request message (JSON body for POST
// and PUT, then path and query parameters via bind), calls the RPC with a
// deadline and writes the response message with okStatus.
func rpc[Req any, PReq interface {
	*Req
	proto.Message
}, Resp proto.Message](
	timeout time.Duration,
	okStatus int,
	bind func(*http.Request, PReq) error,
	call func(context.Context, PReq, ...grpc.CallOption) (Resp, error),
) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		req := PReq(new(Req))
		if r.Method == http.MethodPost || r.Method == http.MethodPut {
			body, err := io.ReadAll(r.Body)
			if err != nil {
				var tooLarge *http.MaxBytesError
				if errors.As(err, &tooLarge) {
					writeError(w, http.StatusRequestEntityTooLarge, "request body too large")
				} else {
					writeError(w, http.StatusBadRequest, "could not read request body")
				}
				return
			}
			if len(body) > 0 {
				if err := unmarshal.Unmarshal(body, req); err != nil {
					writeError(w, http.StatusBadRequest, "invalid JSON body", err.Error())
					return
				}
			}
		}
		if bind != nil {
			if err := bind(r, req); err != nil {
				writeError(w, http.StatusBadRequest, err.Error())
				return
			}
		}

		ctx, cancel := context.WithTimeout(r.Context(), timeout)
		defer cancel()
		ctx = metadata.AppendToOutgoingContext(ctx, "x-request-id", r.Header.Get(requestIDHeader))
		resp, err := call(ctx, req)
		if err != nil {
			writeRPCError(w, r, err)
			return
		}
		if okStatus == http.StatusNoContent {
			w.WriteHeader(okStatus)
			return
		}
		writeProto(w, okStatus, resp)
	})
}

func writeProto(w http.ResponseWriter, status int, m proto.Message) {
	b, err := marshal.Marshal(m)
	if err != nil {
		slog.Error("marshal response", "err", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write(b)
}

// writeError writes an oj.v1.ErrorResponse, the body of every non-2xx response.
func writeError(w http.ResponseWriter, status int, msg string, details ...string) {
	b, _ := marshal.Marshal(&ojv1.ErrorResponse{Error: msg, Details: details})
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write(b)
}

// httpStatus maps a gRPC code to HTTP (see oj-proto README). public reports
// whether the status message is meant for clients.
func httpStatus(c codes.Code) (code int, public bool) {
	switch c {
	case codes.InvalidArgument:
		return http.StatusUnprocessableEntity, true
	case codes.NotFound:
		return http.StatusNotFound, true
	case codes.AlreadyExists, codes.FailedPrecondition:
		return http.StatusConflict, true
	case codes.ResourceExhausted:
		return http.StatusTooManyRequests, true
	case codes.DeadlineExceeded:
		return http.StatusGatewayTimeout, false
	case codes.Unavailable:
		return http.StatusServiceUnavailable, false
	default:
		return http.StatusBadGateway, false
	}
}

func writeRPCError(w http.ResponseWriter, r *http.Request, err error) {
	if r.Context().Err() != nil {
		writeError(w, 499, "client closed request") // nobody is listening
		return
	}
	st := status.Convert(err)
	code, public := httpStatus(st.Code())
	if public {
		writeError(w, code, st.Message())
		return
	}
	slog.Error("upstream error", "id", r.Header.Get(requestIDHeader), "route", r.Pattern,
		"code", st.Code().String(), "err", st.Message())
	switch code {
	case http.StatusGatewayTimeout:
		writeError(w, code, "upstream timed out")
	case http.StatusServiceUnavailable:
		writeError(w, code, "service unavailable")
	default:
		writeError(w, code, "upstream error")
	}
}

// ---------- path and query parameters ----------

var idParam = regexp.MustCompile(`^[1-9][0-9]{0,17}$`)

func parseID(name, v string) (int64, error) {
	if !idParam.MatchString(v) {
		return 0, fmt.Errorf("invalid %s: must be a positive integer", name)
	}
	return strconv.ParseInt(v, 10, 64)
}

func pathID(r *http.Request, name string, dst *int64) error {
	id, err := parseID(name, r.PathValue(name))
	*dst = id
	return err
}

func queryInt32(name, v string, dst *int32) error {
	if v == "" {
		return nil
	}
	n, err := strconv.ParseInt(v, 10, 32)
	if err != nil || n < 0 {
		return fmt.Errorf("invalid %s: must be a non-negative integer", name)
	}
	*dst = int32(n)
	return nil
}

// bindSubmissionQuery reads ?problemId=&username=&limit=&offset= (problem_id
// is accepted too for older clients).
func bindSubmissionQuery(r *http.Request, m *ojv1.ListSubmissionSummariesRequest) error {
	q := r.URL.Query()
	pid := q.Get("problemId")
	if pid == "" {
		pid = q.Get("problem_id")
	}
	if pid != "" {
		id, err := parseID("problemId", pid)
		if err != nil {
			return err
		}
		m.ProblemId = id
	}
	m.Username = q.Get("username")
	if err := queryInt32("limit", q.Get("limit"), &m.Limit); err != nil {
		return err
	}
	return queryInt32("offset", q.Get("offset"), &m.Offset)
}

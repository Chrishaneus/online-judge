// Package api exposes the executor over JSON/HTTP.
package api

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"time"

	"github.com/online-judge/oj-runner/internal/executor"
	"github.com/online-judge/oj-runner/internal/lang"
)

const maxBodyBytes = 64 << 20

// Executor is the subset of *executor.Executor used by the API.
type Executor interface {
	Execute(ctx context.Context, req executor.Request) (executor.Response, error)
	Workers() int
}

type Server struct {
	exec Executor
	mux  *http.ServeMux
}

func New(e Executor) *Server {
	s := &Server{exec: e, mux: http.NewServeMux()}
	s.mux.HandleFunc("GET /healthz", s.health)
	s.mux.HandleFunc("GET /languages", s.languages)
	s.mux.HandleFunc("POST /execute", s.execute)
	return s
}

func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	s.mux.ServeHTTP(w, r)
	if r.URL.Path != "/healthz" {
		slog.Info("request", "method", r.Method, "path", r.URL.Path, "duration", time.Since(start))
	}
}

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "workers": s.exec.Workers()})
}

func (s *Server) languages(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, lang.All())
}

func (s *Server) execute(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, maxBodyBytes)
	var req executor.Request
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body: "+err.Error())
		return
	}
	resp, err := s.exec.Execute(r.Context(), req)
	if err != nil {
		var ve *executor.ValidationError
		switch {
		case errors.As(err, &ve):
			writeError(w, http.StatusBadRequest, ve.Msg)
		case errors.Is(err, context.Canceled), errors.Is(err, context.DeadlineExceeded):
			writeError(w, http.StatusServiceUnavailable, "request cancelled")
		default:
			slog.Error("execute failed", "err", err)
			writeError(w, http.StatusInternalServerError, "internal error")
		}
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

// Package api exposes the Store over an internal JSON/HTTP interface.
package api

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strconv"
	"time"

	"github.com/online-judge/oj-dao/internal/store"
)

// maxBodyBytes caps request bodies (sources and test data can be large-ish).
const maxBodyBytes = 8 << 20

type Server struct {
	store store.Store
	mux   *http.ServeMux
}

func New(s store.Store) *Server {
	srv := &Server{store: s, mux: http.NewServeMux()}
	srv.routes()
	return srv
}

func (s *Server) routes() {
	s.mux.HandleFunc("GET /healthz", s.health)

	s.mux.HandleFunc("GET /problems", s.listProblems)
	s.mux.HandleFunc("POST /problems", s.createProblem)
	s.mux.HandleFunc("GET /problems/{id}", s.getProblem)
	s.mux.HandleFunc("PUT /problems/{id}", s.updateProblem)
	s.mux.HandleFunc("DELETE /problems/{id}", s.deleteProblem)

	s.mux.HandleFunc("GET /problems/{id}/testcases", s.listTestCases)
	s.mux.HandleFunc("POST /problems/{id}/testcases", s.createTestCase)
	s.mux.HandleFunc("DELETE /problems/{id}/testcases/{tcid}", s.deleteTestCase)

	s.mux.HandleFunc("GET /submissions", s.listSubmissions)
	s.mux.HandleFunc("POST /submissions", s.createSubmission)
	s.mux.HandleFunc("GET /submissions/{id}", s.getSubmission)
	s.mux.HandleFunc("PATCH /submissions/{id}", s.updateSubmission)
}

// ServeHTTP adds request logging around the router.
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
	s.mux.ServeHTTP(rec, r)
	if r.URL.Path != "/healthz" {
		slog.Info("request", "method", r.Method, "path", r.URL.Path,
			"status", rec.status, "duration", time.Since(start))
	}
}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	if err := s.store.Ping(r.Context()); err != nil {
		writeError(w, http.StatusServiceUnavailable, "database unavailable")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// ---------- helpers ----------

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(code int) {
	r.status = code
	r.ResponseWriter.WriteHeader(code)
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

// writeStoreError maps store errors to HTTP status codes.
func writeStoreError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, store.ErrNotFound):
		writeError(w, http.StatusNotFound, "not found")
	case errors.Is(err, store.ErrConflict):
		writeError(w, http.StatusConflict, "already exists")
	default:
		slog.Error("store error", "err", err)
		writeError(w, http.StatusInternalServerError, "internal error")
	}
}

func decode(w http.ResponseWriter, r *http.Request, v any) bool {
	r.Body = http.MaxBytesReader(w, r.Body, maxBodyBytes)
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(v); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body: "+err.Error())
		return false
	}
	return true
}

func pathID(w http.ResponseWriter, r *http.Request, name string) (int64, bool) {
	id, err := strconv.ParseInt(r.PathValue(name), 10, 64)
	if err != nil || id <= 0 {
		writeError(w, http.StatusBadRequest, "invalid "+name)
		return 0, false
	}
	return id, true
}

func queryInt(r *http.Request, name string, def int) (int, error) {
	v := r.URL.Query().Get(name)
	if v == "" {
		return def, nil
	}
	n, err := strconv.Atoi(v)
	if err != nil || n < 0 {
		return 0, errors.New("invalid " + name)
	}
	return n, nil
}

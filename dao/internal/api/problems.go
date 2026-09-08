package api

import (
	"net/http"
	"strings"

	"github.com/online-judge/oj-dao/internal/store"
)

type problemInput struct {
	Slug          string `json:"slug"`
	Title         string `json:"title"`
	Statement     string `json:"statement"`
	Difficulty    string `json:"difficulty"`
	TimeLimitMs   int    `json:"time_limit_ms"`
	MemoryLimitMb int    `json:"memory_limit_mb"`
}

func (in problemInput) toProblem() (store.Problem, string) {
	p := store.Problem{
		Slug:          strings.TrimSpace(in.Slug),
		Title:         strings.TrimSpace(in.Title),
		Statement:     in.Statement,
		Difficulty:    strings.TrimSpace(in.Difficulty),
		TimeLimitMs:   in.TimeLimitMs,
		MemoryLimitMb: in.MemoryLimitMb,
	}
	if p.Slug == "" || p.Title == "" {
		return p, "slug and title are required"
	}
	if p.Difficulty == "" {
		p.Difficulty = "easy"
	}
	if p.TimeLimitMs <= 0 {
		p.TimeLimitMs = 2000
	}
	if p.MemoryLimitMb <= 0 {
		p.MemoryLimitMb = 256
	}
	return p, ""
}

func (s *Server) listProblems(w http.ResponseWriter, r *http.Request) {
	ps, err := s.store.ListProblems(r.Context())
	if err != nil {
		writeStoreError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, ps)
}

func (s *Server) getProblem(w http.ResponseWriter, r *http.Request) {
	id, ok := pathID(w, r, "id")
	if !ok {
		return
	}
	p, err := s.store.GetProblem(r.Context(), id)
	if err != nil {
		writeStoreError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, p)
}

func (s *Server) createProblem(w http.ResponseWriter, r *http.Request) {
	var in problemInput
	if !decode(w, r, &in) {
		return
	}
	p, msg := in.toProblem()
	if msg != "" {
		writeError(w, http.StatusBadRequest, msg)
		return
	}
	created, err := s.store.CreateProblem(r.Context(), p)
	if err != nil {
		writeStoreError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, created)
}

func (s *Server) updateProblem(w http.ResponseWriter, r *http.Request) {
	id, ok := pathID(w, r, "id")
	if !ok {
		return
	}
	var in problemInput
	if !decode(w, r, &in) {
		return
	}
	p, msg := in.toProblem()
	if msg != "" {
		writeError(w, http.StatusBadRequest, msg)
		return
	}
	p.ID = id
	updated, err := s.store.UpdateProblem(r.Context(), p)
	if err != nil {
		writeStoreError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, updated)
}

func (s *Server) deleteProblem(w http.ResponseWriter, r *http.Request) {
	id, ok := pathID(w, r, "id")
	if !ok {
		return
	}
	if err := s.store.DeleteProblem(r.Context(), id); err != nil {
		writeStoreError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

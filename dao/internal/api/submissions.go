package api

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/online-judge/oj-dao/internal/store"
)

type submissionInput struct {
	ProblemID int64  `json:"problem_id"`
	Username  string `json:"username"`
	Language  string `json:"language"`
	Source    string `json:"source"`
}

func (s *Server) createSubmission(w http.ResponseWriter, r *http.Request) {
	var in submissionInput
	if !decode(w, r, &in) {
		return
	}
	if in.ProblemID <= 0 || strings.TrimSpace(in.Language) == "" || in.Source == "" {
		writeError(w, http.StatusBadRequest, "problem_id, language and source are required")
		return
	}
	if strings.TrimSpace(in.Username) == "" {
		in.Username = "anonymous"
	}
	sub, err := s.store.CreateSubmission(r.Context(), store.Submission{
		ProblemID: in.ProblemID,
		Username:  strings.TrimSpace(in.Username),
		Language:  strings.TrimSpace(in.Language),
		Source:    in.Source,
		Status:    store.StatusPending,
	})
	if err != nil {
		writeStoreError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, sub)
}

func (s *Server) getSubmission(w http.ResponseWriter, r *http.Request) {
	id, ok := pathID(w, r, "id")
	if !ok {
		return
	}
	sub, err := s.store.GetSubmission(r.Context(), id)
	if err != nil {
		writeStoreError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, sub)
}

func (s *Server) listSubmissions(w http.ResponseWriter, r *http.Request) {
	var f store.SubmissionFilter
	if v := r.URL.Query().Get("problem_id"); v != "" {
		id, err := strconv.ParseInt(v, 10, 64)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid problem_id")
			return
		}
		f.ProblemID = id
	}
	f.Username = r.URL.Query().Get("username")
	var err error
	if f.Limit, err = queryInt(r, "limit", 50); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if f.Limit > 500 {
		f.Limit = 500
	}
	if f.Offset, err = queryInt(r, "offset", 0); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	subs, err := s.store.ListSubmissions(r.Context(), f)
	if err != nil {
		writeStoreError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, subs)
}

var validStatuses = map[string]bool{
	store.StatusPending: true, store.StatusJudging: true,
	store.StatusFinished: true, store.StatusFailed: true,
}

func (s *Server) updateSubmission(w http.ResponseWriter, r *http.Request) {
	id, ok := pathID(w, r, "id")
	if !ok {
		return
	}
	var u store.SubmissionUpdate
	if !decode(w, r, &u) {
		return
	}
	if u.Status != nil && !validStatuses[*u.Status] {
		writeError(w, http.StatusBadRequest, "invalid status")
		return
	}
	sub, err := s.store.UpdateSubmission(r.Context(), id, u)
	if err != nil {
		writeStoreError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, sub)
}

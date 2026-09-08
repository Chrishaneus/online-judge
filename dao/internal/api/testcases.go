package api

import (
	"net/http"

	"github.com/online-judge/oj-dao/internal/store"
)

type testCaseInput struct {
	Input          string `json:"input"`
	ExpectedOutput string `json:"expected_output"`
	IsSample       bool   `json:"is_sample"`
	Ordinal        int    `json:"ordinal"`
}

func (s *Server) listTestCases(w http.ResponseWriter, r *http.Request) {
	id, ok := pathID(w, r, "id")
	if !ok {
		return
	}
	samplesOnly := r.URL.Query().Get("samples_only") == "true"
	tcs, err := s.store.ListTestCases(r.Context(), id, samplesOnly)
	if err != nil {
		writeStoreError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, tcs)
}

func (s *Server) createTestCase(w http.ResponseWriter, r *http.Request) {
	id, ok := pathID(w, r, "id")
	if !ok {
		return
	}
	var in testCaseInput
	if !decode(w, r, &in) {
		return
	}
	tc, err := s.store.CreateTestCase(r.Context(), store.TestCase{
		ProblemID:      id,
		Input:          in.Input,
		ExpectedOutput: in.ExpectedOutput,
		IsSample:       in.IsSample,
		Ordinal:        in.Ordinal,
	})
	if err != nil {
		writeStoreError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, tc)
}

func (s *Server) deleteTestCase(w http.ResponseWriter, r *http.Request) {
	id, ok := pathID(w, r, "id")
	if !ok {
		return
	}
	tcid, ok := pathID(w, r, "tcid")
	if !ok {
		return
	}
	if err := s.store.DeleteTestCase(r.Context(), id, tcid); err != nil {
		writeStoreError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

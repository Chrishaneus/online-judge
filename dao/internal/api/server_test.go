package api

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/online-judge/oj-dao/internal/store"
)

func do(t *testing.T, h http.Handler, method, path string, body any) *httptest.ResponseRecorder {
	t.Helper()
	var buf bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&buf).Encode(body); err != nil {
			t.Fatal(err)
		}
	}
	req := httptest.NewRequest(method, path, &buf)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func decodeInto[T any](t *testing.T, rec *httptest.ResponseRecorder) T {
	t.Helper()
	var v T
	if err := json.Unmarshal(rec.Body.Bytes(), &v); err != nil {
		t.Fatalf("decode %q: %v", rec.Body.String(), err)
	}
	return v
}

func expectStatus(t *testing.T, rec *httptest.ResponseRecorder, want int) {
	t.Helper()
	if rec.Code != want {
		t.Fatalf("status = %d, want %d; body=%s", rec.Code, want, rec.Body.String())
	}
}

func newProblem(t *testing.T, h http.Handler, slug string) store.Problem {
	t.Helper()
	rec := do(t, h, "POST", "/problems", map[string]any{"slug": slug, "title": "T " + slug, "statement": "s"})
	expectStatus(t, rec, http.StatusCreated)
	return decodeInto[store.Problem](t, rec)
}

func TestHealth(t *testing.T) {
	h := New(store.NewMemory())
	expectStatus(t, do(t, h, "GET", "/healthz", nil), http.StatusOK)
}

func TestProblemCRUD(t *testing.T) {
	h := New(store.NewMemory())

	p := newProblem(t, h, "sum")
	if p.ID == 0 || p.TimeLimitMs != 2000 || p.MemoryLimitMb != 256 || p.Difficulty != "easy" {
		t.Fatalf("defaults not applied: %+v", p)
	}

	// duplicate slug -> 409
	expectStatus(t, do(t, h, "POST", "/problems", map[string]any{"slug": "sum", "title": "x"}), http.StatusConflict)
	// missing title -> 400
	expectStatus(t, do(t, h, "POST", "/problems", map[string]any{"slug": "y"}), http.StatusBadRequest)
	// unknown field -> 400
	expectStatus(t, do(t, h, "POST", "/problems", map[string]any{"slug": "z", "title": "z", "bogus": 1}), http.StatusBadRequest)

	rec := do(t, h, "PUT", fmt.Sprintf("/problems/%d", p.ID),
		map[string]any{"slug": "sum", "title": "Sum!", "time_limit_ms": 500})
	expectStatus(t, rec, http.StatusOK)
	if got := decodeInto[store.Problem](t, rec); got.Title != "Sum!" || got.TimeLimitMs != 500 {
		t.Fatalf("update not applied: %+v", got)
	}

	rec = do(t, h, "GET", "/problems", nil)
	expectStatus(t, rec, http.StatusOK)
	if ps := decodeInto[[]store.Problem](t, rec); len(ps) != 1 {
		t.Fatalf("want 1 problem, got %d", len(ps))
	}

	expectStatus(t, do(t, h, "DELETE", fmt.Sprintf("/problems/%d", p.ID), nil), http.StatusNoContent)
	expectStatus(t, do(t, h, "GET", fmt.Sprintf("/problems/%d", p.ID), nil), http.StatusNotFound)
	expectStatus(t, do(t, h, "GET", "/problems/abc", nil), http.StatusBadRequest)
}

func TestTestCases(t *testing.T) {
	h := New(store.NewMemory())
	p := newProblem(t, h, "tc")
	base := fmt.Sprintf("/problems/%d/testcases", p.ID)

	expectStatus(t, do(t, h, "POST", base, map[string]any{"input": "1", "expected_output": "1", "is_sample": true, "ordinal": 2}), http.StatusCreated)
	rec := do(t, h, "POST", base, map[string]any{"input": "2", "expected_output": "4", "ordinal": 1})
	expectStatus(t, rec, http.StatusCreated)
	hidden := decodeInto[store.TestCase](t, rec)

	all := decodeInto[[]store.TestCase](t, do(t, h, "GET", base, nil))
	if len(all) != 2 || all[0].Ordinal != 1 {
		t.Fatalf("want 2 ordered cases, got %+v", all)
	}
	samples := decodeInto[[]store.TestCase](t, do(t, h, "GET", base+"?samples_only=true", nil))
	if len(samples) != 1 || !samples[0].IsSample {
		t.Fatalf("want 1 sample, got %+v", samples)
	}

	expectStatus(t, do(t, h, "DELETE", fmt.Sprintf("%s/%d", base, hidden.ID), nil), http.StatusNoContent)
	expectStatus(t, do(t, h, "DELETE", fmt.Sprintf("%s/%d", base, hidden.ID), nil), http.StatusNotFound)
	expectStatus(t, do(t, h, "POST", "/problems/999/testcases", map[string]any{"input": "1"}), http.StatusNotFound)
}

func TestSubmissions(t *testing.T) {
	h := New(store.NewMemory())
	p := newProblem(t, h, "subs")

	expectStatus(t, do(t, h, "POST", "/submissions", map[string]any{"problem_id": p.ID}), http.StatusBadRequest)
	expectStatus(t, do(t, h, "POST", "/submissions",
		map[string]any{"problem_id": 999, "language": "python", "source": "x"}), http.StatusNotFound)

	rec := do(t, h, "POST", "/submissions",
		map[string]any{"problem_id": p.ID, "language": "python", "source": "print(1)"})
	expectStatus(t, rec, http.StatusCreated)
	sub := decodeInto[store.Submission](t, rec)
	if sub.Status != store.StatusPending || sub.Username != "anonymous" || string(sub.Results) != "[]" {
		t.Fatalf("unexpected defaults: %+v", sub)
	}
	do(t, h, "POST", "/submissions", map[string]any{"problem_id": p.ID, "username": "bob", "language": "cpp", "source": "y"})

	rec = do(t, h, "PATCH", fmt.Sprintf("/submissions/%d", sub.ID), map[string]any{
		"status": "FINISHED", "verdict": "AC", "passed": 3, "total": 3, "results": []map[string]any{{"verdict": "AC"}},
	})
	expectStatus(t, rec, http.StatusOK)
	upd := decodeInto[store.Submission](t, rec)
	if upd.Verdict != "AC" || upd.Passed != 3 || upd.Language != "python" {
		t.Fatalf("patch not applied: %+v", upd)
	}
	expectStatus(t, do(t, h, "PATCH", fmt.Sprintf("/submissions/%d", sub.ID), map[string]any{"status": "NOPE"}), http.StatusBadRequest)

	list := decodeInto[[]store.Submission](t, do(t, h, "GET", "/submissions?username=bob", nil))
	if len(list) != 1 || list[0].Username != "bob" {
		t.Fatalf("filter failed: %+v", list)
	}
	list = decodeInto[[]store.Submission](t, do(t, h, "GET", fmt.Sprintf("/submissions?problem_id=%d&limit=1", p.ID), nil))
	if len(list) != 1 || list[0].Username != "bob" {
		t.Fatalf("want newest first with limit 1: %+v", list)
	}
	expectStatus(t, do(t, h, "GET", "/submissions?limit=-1", nil), http.StatusBadRequest)
}

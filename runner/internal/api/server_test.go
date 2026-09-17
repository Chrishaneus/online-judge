package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/online-judge/oj-runner/internal/executor"
)

type fakeExec struct {
	resp executor.Response
	err  error
	got  executor.Request
}

func (f *fakeExec) Execute(_ context.Context, req executor.Request) (executor.Response, error) {
	f.got = req
	return f.resp, f.err
}
func (f *fakeExec) Workers() int { return 3 }

func post(h http.Handler, body string) *httptest.ResponseRecorder {
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest("POST", "/execute", strings.NewReader(body)))
	return rec
}

func TestExecuteOK(t *testing.T) {
	f := &fakeExec{resp: executor.Response{Status: "OK", Results: []executor.TestResult{{ID: "a", Status: "OK", Stdout: "3\n"}}}}
	rec := post(New(f), `{"language":"python","source":"print(3)","tests":[{"id":"a","stdin":""}],"time_limit_ms":500}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("status %d: %s", rec.Code, rec.Body)
	}
	var resp executor.Response
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatal(err)
	}
	if resp.Results[0].Stdout != "3\n" || f.got.TimeLimitMs != 500 || f.got.Tests[0].ID != "a" {
		t.Fatalf("unexpected: resp=%+v got=%+v", resp, f.got)
	}
}

func TestExecuteErrors(t *testing.T) {
	cases := []struct {
		err  error
		body string
		want int
	}{
		{nil, "{not json", http.StatusBadRequest},
		{&executor.ValidationError{Msg: "nope"}, `{}`, http.StatusBadRequest},
		{context.Canceled, `{}`, http.StatusServiceUnavailable},
		{errors.New("boom"), `{}`, http.StatusInternalServerError},
	}
	for i, c := range cases {
		rec := post(New(&fakeExec{err: c.err}), c.body)
		if rec.Code != c.want {
			t.Errorf("case %d: status %d want %d", i, rec.Code, c.want)
		}
	}
}

func TestLanguagesAndHealth(t *testing.T) {
	h := New(&fakeExec{})
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest("GET", "/languages", nil))
	var langs []map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &langs); err != nil || len(langs) != 4 {
		t.Fatalf("languages: %v %s", err, rec.Body)
	}
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest("GET", "/healthz", nil))
	if rec.Code != 200 || !strings.Contains(rec.Body.String(), `"workers":3`) {
		t.Fatalf("health: %d %s", rec.Code, rec.Body)
	}
}

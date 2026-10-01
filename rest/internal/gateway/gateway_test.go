package gateway

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
)

// upstreamEcho reports what the midlayer would have received.
type seen struct {
	Method, Path, Query, Body, Auth, RequestID, XFF string
}

func newGateway(t *testing.T, cfg Config) (*Gateway, *seen, func()) {
	t.Helper()
	got := &seen{}
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		*got = seen{r.Method, r.URL.Path, r.URL.RawQuery, string(b), r.Header.Get("Authorization"),
			r.Header.Get("X-Request-ID"), r.Header.Get("X-Forwarded-For")}
		writeJSON(w, http.StatusOK, map[string]string{"ok": "yes"})
	}))
	u, _ := url.Parse(up.URL)
	cfg.MidlayerURL = u
	if cfg.RateLimitPerMin == 0 {
		cfg.RateLimitPerMin, cfg.RateLimitBurst = 600, 100
	}
	return New(cfg), got, up.Close
}

func call(g http.Handler, method, path, body string, hdr map[string]string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	g.ServeHTTP(rec, req)
	return rec
}

func TestPublicRouting(t *testing.T) {
	g, got, done := newGateway(t, Config{})
	defer done()

	cases := []struct{ method, path, wantPath string }{
		{"GET", "/api/v1/problems", "/problems"},
		{"GET", "/api/v1/problems/12", "/problems/12"},
		{"GET", "/api/v1/languages", "/languages"},
		{"GET", "/api/v1/status", "/readyz"},
		{"GET", "/api/v1/submissions?problem_id=3&limit=5", "/submissions"},
		{"GET", "/api/v1/submissions/7", "/submissions/7"},
		{"POST", "/api/v1/submissions", "/submissions"},
		{"POST", "/api/v1/run", "/run"},
	}
	for _, c := range cases {
		rec := call(g, c.method, c.path, `{"a":1}`, nil)
		if rec.Code != 200 || got.Path != c.wantPath || got.Method != c.method {
			t.Errorf("%s %s -> %d upstream %s %s", c.method, c.path, rec.Code, got.Method, got.Path)
		}
	}
	call(g, "GET", "/api/v1/submissions?problem_id=3&limit=5", "", nil)
	if got.Query != "problem_id=3&limit=5" {
		t.Errorf("query not forwarded: %q", got.Query)
	}
	call(g, "POST", "/api/v1/run", `{"x":"y"}`, nil)
	if got.Body != `{"x":"y"}` || got.RequestID == "" || got.XFF == "" {
		t.Errorf("body/headers not forwarded: %+v", got)
	}
}

func TestUnknownAndInvalidRoutes(t *testing.T) {
	g, got, done := newGateway(t, Config{})
	defer done()
	*got = seen{}
	for _, p := range []string{"/api/v1/readyz", "/problems", "/api/v1/problems/abc", "/api/v1/problems/0", "/api/v1/problems/-1"} {
		rec := call(g, "GET", p, "", nil)
		if rec.Code != 404 && rec.Code != 400 {
			t.Errorf("%s: got %d", p, rec.Code)
		}
	}
	if got.Path != "" {
		t.Fatalf("nothing should have reached upstream, got %s", got.Path)
	}
	// Admin-only mutation is not exposed publicly.
	if rec := call(g, "DELETE", "/api/v1/problems/1", "", nil); rec.Code != 404 {
		t.Fatalf("public delete should 404, got %d", rec.Code)
	}
}

func TestAdminRoutes(t *testing.T) {
	g, got, done := newGateway(t, Config{AdminToken: "s3cret"})
	defer done()
	auth := map[string]string{"Authorization": "Bearer s3cret"}

	if rec := call(g, "POST", "/api/v1/admin/problems", "{}", nil); rec.Code != 401 {
		t.Fatalf("missing token: %d", rec.Code)
	}
	cases := []struct{ method, path, wantPath string }{
		{"POST", "/api/v1/admin/problems", "/problems"},
		{"PUT", "/api/v1/admin/problems/4", "/problems/4"},
		{"DELETE", "/api/v1/admin/problems/4", "/problems/4"},
		{"GET", "/api/v1/admin/problems/4/testcases", "/problems/4/testcases"},
		{"POST", "/api/v1/admin/problems/4/testcases", "/problems/4/testcases"},
		{"DELETE", "/api/v1/admin/problems/4/testcases/9", "/problems/4/testcases/9"},
	}
	for _, c := range cases {
		rec := call(g, c.method, c.path, "{}", auth)
		if rec.Code != 200 || got.Path != c.wantPath {
			t.Errorf("%s %s -> %d upstream %s", c.method, c.path, rec.Code, got.Path)
		}
		if got.Auth != "" {
			t.Errorf("Authorization header leaked upstream")
		}
	}
	rec := call(g, "GET", "/api/v1/admin/verify", "", auth)
	var body map[string]bool
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if rec.Code != 200 || !body["admin"] {
		t.Fatalf("verify: %d %s", rec.Code, rec.Body)
	}
}

func TestSubmissionRateLimited(t *testing.T) {
	g, _, done := newGateway(t, Config{RateLimitPerMin: 1, RateLimitBurst: 2})
	defer done()
	codes := []int{}
	for i := 0; i < 3; i++ {
		codes = append(codes, call(g, "POST", "/api/v1/submissions", "{}", nil).Code)
	}
	if codes[0] != 200 || codes[1] != 200 || codes[2] != 429 {
		t.Fatalf("codes = %v", codes)
	}
	// Reads are never rate limited.
	if rec := call(g, "GET", "/api/v1/problems", "", nil); rec.Code != 200 {
		t.Fatalf("read was limited: %d", rec.Code)
	}
}

func TestUpstreamDown(t *testing.T) {
	g, _, done := newGateway(t, Config{})
	done() // stop upstream
	rec := call(g, "GET", "/api/v1/problems", "", nil)
	if rec.Code != http.StatusBadGateway || !strings.Contains(rec.Body.String(), "upstream unavailable") {
		t.Fatalf("got %d %s", rec.Code, rec.Body)
	}
}

func TestHealthz(t *testing.T) {
	g, _, done := newGateway(t, Config{})
	defer done()
	if rec := call(g, "GET", "/healthz", "", nil); rec.Code != 200 {
		t.Fatalf("healthz %d", rec.Code)
	}
}

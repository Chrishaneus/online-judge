package gateway

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

var okHandler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) })

func TestRequireAdmin(t *testing.T) {
	cases := []struct {
		configured, header string
		want               int
	}{
		{"", "Bearer x", http.StatusForbidden},
		{"secret", "", http.StatusUnauthorized},
		{"secret", "Bearer wrong", http.StatusUnauthorized},
		{"secret", "secret", http.StatusUnauthorized},
		{"secret", "Bearer secret", http.StatusOK},
	}
	for _, c := range cases {
		req := httptest.NewRequest("GET", "/", nil)
		if c.header != "" {
			req.Header.Set("Authorization", c.header)
		}
		rec := httptest.NewRecorder()
		RequireAdmin(c.configured)(okHandler).ServeHTTP(rec, req)
		if rec.Code != c.want {
			t.Errorf("token=%q header=%q: got %d want %d", c.configured, c.header, rec.Code, c.want)
		}
	}
}

func TestCORS(t *testing.T) {
	h := CORS([]string{"https://oj.example"})(okHandler)

	req := httptest.NewRequest("OPTIONS", "/api/v1/run", nil)
	req.Header.Set("Origin", "https://oj.example")
	req.Header.Set("Access-Control-Request-Method", "POST")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusNoContent || rec.Header().Get("Access-Control-Allow-Origin") != "https://oj.example" {
		t.Fatalf("preflight failed: %d %v", rec.Code, rec.Header())
	}

	req = httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Origin", "https://evil.example")
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Header().Get("Access-Control-Allow-Origin") != "" {
		t.Fatal("disallowed origin must not get CORS headers")
	}
}

func TestRequestID(t *testing.T) {
	var seen string
	h := RequestID()(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { seen = r.Header.Get(requestIDHeader) }))

	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest("GET", "/", nil))
	if seen == "" || rec.Header().Get(requestIDHeader) != seen {
		t.Fatalf("generated id not propagated: %q / %q", seen, rec.Header().Get(requestIDHeader))
	}

	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set(requestIDHeader, "abc-123")
	h.ServeHTTP(httptest.NewRecorder(), req)
	if seen != "abc-123" {
		t.Fatalf("valid client id should be kept, got %q", seen)
	}

	req = httptest.NewRequest("GET", "/", nil)
	req.Header.Set(requestIDHeader, "bad id\nwith newline")
	h.ServeHTTP(httptest.NewRecorder(), req)
	if seen == "bad id\nwith newline" {
		t.Fatal("invalid client id must be replaced")
	}
}

func TestClientIP(t *testing.T) {
	req := httptest.NewRequest("GET", "/", nil)
	req.RemoteAddr = "10.0.0.1:5555"
	req.Header.Set("X-Forwarded-For", "1.2.3.4, 10.0.0.1")
	if ip := ClientIP(req, false); ip != "10.0.0.1" {
		t.Fatalf("untrusted: got %s", ip)
	}
	if ip := ClientIP(req, true); ip != "1.2.3.4" {
		t.Fatalf("trusted xff: got %s", ip)
	}
	req.Header.Set("X-Real-IP", "5.6.7.8")
	if ip := ClientIP(req, true); ip != "5.6.7.8" {
		t.Fatalf("trusted x-real-ip: got %s", ip)
	}
}

func TestRateLimitMiddleware(t *testing.T) {
	h := RateLimit(NewRateLimiter(1, 1), false)(okHandler)
	req := httptest.NewRequest("POST", "/", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("first request: %d", rec.Code)
	}
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusTooManyRequests || rec.Header().Get("Retry-After") == "" {
		t.Fatalf("second request: %d %v", rec.Code, rec.Header())
	}
}

func TestRecover(t *testing.T) {
	h := Recover()(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { panic("boom") }))
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest("GET", "/", nil))
	if rec.Code != 500 || !strings.Contains(rec.Body.String(), "internal error") {
		t.Fatalf("got %d %s", rec.Code, rec.Body)
	}
}

func TestMaxBody(t *testing.T) {
	h := MaxBody(4)(okHandler)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest("POST", "/", strings.NewReader("too long")))
	if rec.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf("got %d", rec.Code)
	}
}

// Package gateway implements the public REST edge of the online judge: an
// explicit allowlist of routes reverse-proxied to the midlayer, wrapped in
// auth, rate limiting, CORS and observability middleware.
package gateway

import (
	"context"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"regexp"
	"time"
)

type Config struct {
	MidlayerURL     *url.URL
	AdminToken      string
	CORSOrigins     []string
	RateLimitPerMin int
	RateLimitBurst  int
	TrustProxy      bool
	UpstreamTimeout time.Duration
}

type Gateway struct {
	cfg     Config
	proxy   *httputil.ReverseProxy
	handler http.Handler
}

const (
	maxSubmissionBody = 512 << 10
	maxRunBody        = 2 << 20
	maxAdminBody      = 64 << 20
)

func New(cfg Config) *Gateway {
	if cfg.UpstreamTimeout <= 0 {
		cfg.UpstreamTimeout = 2 * time.Minute
	}
	g := &Gateway{cfg: cfg}
	g.proxy = &httputil.ReverseProxy{
		Rewrite: func(pr *httputil.ProxyRequest) {
			pr.SetURL(cfg.MidlayerURL)
			pr.SetXForwarded()
			pr.Out.Header.Del("Authorization") // never leak credentials downstream
			pr.Out.Header.Del("Cookie")
		},
		Transport: &http.Transport{
			DialContext:           (&net.Dialer{Timeout: 5 * time.Second}).DialContext,
			ResponseHeaderTimeout: cfg.UpstreamTimeout,
			MaxIdleConnsPerHost:   32,
			IdleConnTimeout:       90 * time.Second,
		},
		ErrorHandler: func(w http.ResponseWriter, r *http.Request, err error) {
			if errors.Is(err, context.Canceled) {
				return // client went away
			}
			slog.Error("upstream error", "path", r.URL.Path, "err", err)
			writeError(w, http.StatusBadGateway, "upstream unavailable")
		},
	}
	g.handler = chain(g.routes(),
		Recover(),
		RequestID(),
		Logging(),
		CORS(cfg.CORSOrigins),
	)
	return g
}

func (g *Gateway) ServeHTTP(w http.ResponseWriter, r *http.Request) { g.handler.ServeHTTP(w, r) }

var (
	idParam     = regexp.MustCompile(`^[1-9][0-9]{0,17}$`)
	placeholder = regexp.MustCompile(`\{([a-z]+)\}`)
)

// forward proxies to upstreamTemplate, substituting {name} path parameters
// after checking they are positive integers.
func (g *Gateway) forward(upstreamTemplate string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		valid := true
		path := placeholder.ReplaceAllStringFunc(upstreamTemplate, func(m string) string {
			v := r.PathValue(m[1 : len(m)-1])
			if !idParam.MatchString(v) {
				valid = false
			}
			return v
		})
		if !valid {
			writeError(w, http.StatusBadRequest, "invalid id")
			return
		}
		out := r.Clone(r.Context())
		out.URL.Path, out.URL.RawPath = path, ""
		g.proxy.ServeHTTP(w, out)
	})
}

func (g *Gateway) routes() http.Handler {
	mux := http.NewServeMux()
	limited := RateLimit(NewRateLimiter(g.cfg.RateLimitPerMin, g.cfg.RateLimitBurst), g.cfg.TrustProxy)
	admin := RequireAdmin(g.cfg.AdminToken)

	route := func(pattern, upstream string, mws ...Middleware) {
		mux.Handle(pattern, chain(g.forward(upstream), mws...))
	}

	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})

	// Public, read-only.
	route("GET /api/v1/status", "/readyz")
	route("GET /api/v1/languages", "/languages")
	route("GET /api/v1/problems", "/problems")
	route("GET /api/v1/problems/{id}", "/problems/{id}")
	route("GET /api/v1/submissions", "/submissions")
	route("GET /api/v1/submissions/{id}", "/submissions/{id}")

	// Public, executes code: rate limited.
	route("POST /api/v1/submissions", "/submissions", limited, MaxBody(maxSubmissionBody))
	route("POST /api/v1/run", "/run", limited, MaxBody(maxRunBody))

	// Admin.
	mux.Handle("GET /api/v1/admin/verify", admin(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]bool{"admin": true})
	})))
	route("POST /api/v1/admin/problems", "/problems", admin, MaxBody(maxAdminBody))
	route("PUT /api/v1/admin/problems/{id}", "/problems/{id}", admin, MaxBody(maxAdminBody))
	route("DELETE /api/v1/admin/problems/{id}", "/problems/{id}", admin)
	route("GET /api/v1/admin/problems/{id}/testcases", "/problems/{id}/testcases", admin)
	route("POST /api/v1/admin/problems/{id}/testcases", "/problems/{id}/testcases", admin, MaxBody(maxAdminBody))
	route("DELETE /api/v1/admin/problems/{id}/testcases/{tcid}", "/problems/{id}/testcases/{tcid}", admin)

	mux.HandleFunc("/", func(w http.ResponseWriter, _ *http.Request) {
		writeError(w, http.StatusNotFound, "not found")
	})
	return mux
}

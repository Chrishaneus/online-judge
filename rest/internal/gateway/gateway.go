// Package gateway implements the public REST edge of the online judge: each
// /api/v1 route translates canonical proto JSON into one oj.v1.JudgeService
// gRPC call on midlayer, wrapped in auth, rate limiting, CORS and
// observability middleware. It holds no business logic.
package gateway

import (
	"net/http"
	"time"

	ojv1 "github.com/online-judge/online-judge/rest/internal/gen/oj/v1"
)

type Config struct {
	// Client is the midlayer JudgeService client.
	Client          ojv1.JudgeServiceClient
	AdminToken      string
	CORSOrigins     []string
	RateLimitPerMin int
	RateLimitBurst  int
	TrustProxy      bool
	// UpstreamTimeout is the deadline of every gRPC call except RunCode.
	UpstreamTimeout time.Duration
	// RunTimeout is the deadline of RunCode (compile + run on a runner).
	RunTimeout time.Duration
}

type Gateway struct {
	cfg     Config
	handler http.Handler
}

const (
	maxSubmissionBody = 512 << 10
	maxRunBody        = 2 << 20
	maxAdminBody      = 64 << 20
)

func New(cfg Config) *Gateway {
	if cfg.UpstreamTimeout <= 0 {
		cfg.UpstreamTimeout = 60 * time.Second
	}
	if cfg.RunTimeout <= 0 {
		cfg.RunTimeout = cfg.UpstreamTimeout
	}
	g := &Gateway{cfg: cfg}
	g.handler = chain(g.routes(),
		Recover(),
		RequestID(),
		Logging(),
		CORS(cfg.CORSOrigins),
	)
	return g
}

func (g *Gateway) ServeHTTP(w http.ResponseWriter, r *http.Request) { g.handler.ServeHTTP(w, r) }

func (g *Gateway) routes() http.Handler {
	mux := http.NewServeMux()
	c := g.cfg.Client
	t, runT := g.cfg.UpstreamTimeout, g.cfg.RunTimeout
	limited := RateLimit(NewRateLimiter(g.cfg.RateLimitPerMin, g.cfg.RateLimitBurst), g.cfg.TrustProxy)
	admin := RequireAdmin(g.cfg.AdminToken)
	handle := func(pattern string, h http.Handler, mws ...Middleware) { mux.Handle(pattern, chain(h, mws...)) }

	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})

	// Public, read-only.
	handle("GET /api/v1/status", rpc(t, http.StatusOK, nil, c.GetStatus))
	handle("GET /api/v1/languages", rpc(t, http.StatusOK, nil, c.ListLanguages))
	handle("GET /api/v1/problems", rpc(t, http.StatusOK, nil, c.ListProblemSummaries))
	handle("GET /api/v1/problems/{id}", rpc(t, http.StatusOK,
		func(r *http.Request, m *ojv1.GetProblemDetailRequest) error { return pathID(r, "id", &m.Id) },
		c.GetProblemDetail))
	handle("GET /api/v1/submissions", rpc(t, http.StatusOK, bindSubmissionQuery, c.ListSubmissionSummaries))
	handle("GET /api/v1/submissions/{id}", rpc(t, http.StatusOK,
		func(r *http.Request, m *ojv1.GetSubmissionDetailRequest) error { return pathID(r, "id", &m.Id) },
		c.GetSubmissionDetail))

	// Public, executes code: rate limited.
	handle("POST /api/v1/submissions", rpc(t, http.StatusAccepted, nil, c.Submit), limited, MaxBody(maxSubmissionBody))
	handle("POST /api/v1/run", rpc(runT, http.StatusOK, nil, c.RunCode), limited, MaxBody(maxRunBody))

	// Admin.
	handle("GET /api/v1/admin/verify", http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]bool{"admin": true})
	}), admin)
	handle("POST /api/v1/admin/problems", rpc(t, http.StatusCreated, nil, c.AddProblem), admin, MaxBody(maxAdminBody))
	handle("PUT /api/v1/admin/problems/{id}", rpc(t, http.StatusOK,
		func(r *http.Request, m *ojv1.EditProblemRequest) error { return pathID(r, "id", &m.Id) },
		c.EditProblem), admin, MaxBody(maxAdminBody))
	handle("DELETE /api/v1/admin/problems/{id}", rpc(t, http.StatusNoContent,
		func(r *http.Request, m *ojv1.RemoveProblemRequest) error { return pathID(r, "id", &m.Id) },
		c.RemoveProblem), admin)
	handle("GET /api/v1/admin/problems/{problemId}/testcases", rpc(t, http.StatusOK,
		func(r *http.Request, m *ojv1.ListProblemTestCasesRequest) error {
			return pathID(r, "problemId", &m.ProblemId)
		},
		c.ListProblemTestCases), admin)
	handle("POST /api/v1/admin/problems/{problemId}/testcases", rpc(t, http.StatusCreated,
		func(r *http.Request, m *ojv1.AddTestCaseRequest) error { return pathID(r, "problemId", &m.ProblemId) },
		c.AddTestCase), admin, MaxBody(maxAdminBody))
	handle("DELETE /api/v1/admin/problems/{problemId}/testcases/{id}", rpc(t, http.StatusNoContent,
		func(r *http.Request, m *ojv1.RemoveTestCaseRequest) error {
			if err := pathID(r, "problemId", &m.ProblemId); err != nil {
				return err
			}
			return pathID(r, "id", &m.Id)
		},
		c.RemoveTestCase), admin)

	mux.HandleFunc("/", func(w http.ResponseWriter, _ *http.Request) {
		writeError(w, http.StatusNotFound, "not found")
	})
	return mux
}

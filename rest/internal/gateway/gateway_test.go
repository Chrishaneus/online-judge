package gateway

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/timestamppb"

	ojv1 "github.com/online-judge/online-judge/rest/internal/gen/oj/v1"
)

// fakeJudge records the last call and answers with a canned response or err.
type fakeJudge struct {
	ojv1.UnimplementedJudgeServiceServer

	mu     sync.Mutex
	method string
	req    proto.Message
	md     metadata.MD
	err    error
	block  bool // wait for the deadline
	resp   map[string]proto.Message
}

func (f *fakeJudge) last() (string, proto.Message, metadata.MD) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.method, f.req, f.md
}

func handleFake[Resp proto.Message](f *fakeJudge, ctx context.Context, method string, req proto.Message, empty Resp) (Resp, error) {
	f.mu.Lock()
	f.method, f.req = method, req
	f.md, _ = metadata.FromIncomingContext(ctx)
	err, block, canned := f.err, f.block, f.resp[method]
	f.mu.Unlock()
	if block {
		<-ctx.Done()
		return empty, status.FromContextError(ctx.Err()).Err()
	}
	if err != nil {
		return empty, err
	}
	if canned != nil {
		return canned.(Resp), nil
	}
	return empty, nil
}

func (f *fakeJudge) GetStatus(ctx context.Context, r *ojv1.GetStatusRequest) (*ojv1.GetStatusResponse, error) {
	return handleFake(f, ctx, "GetStatus", r, &ojv1.GetStatusResponse{})
}
func (f *fakeJudge) ListLanguages(ctx context.Context, r *ojv1.ListLanguagesRequest) (*ojv1.ListLanguagesResponse, error) {
	return handleFake(f, ctx, "ListLanguages", r, &ojv1.ListLanguagesResponse{})
}
func (f *fakeJudge) ListProblemSummaries(ctx context.Context, r *ojv1.ListProblemSummariesRequest) (*ojv1.ListProblemSummariesResponse, error) {
	return handleFake(f, ctx, "ListProblemSummaries", r, &ojv1.ListProblemSummariesResponse{})
}
func (f *fakeJudge) GetProblemDetail(ctx context.Context, r *ojv1.GetProblemDetailRequest) (*ojv1.GetProblemDetailResponse, error) {
	return handleFake(f, ctx, "GetProblemDetail", r, &ojv1.GetProblemDetailResponse{})
}
func (f *fakeJudge) Submit(ctx context.Context, r *ojv1.SubmitRequest) (*ojv1.SubmitResponse, error) {
	return handleFake(f, ctx, "Submit", r, &ojv1.SubmitResponse{})
}
func (f *fakeJudge) ListSubmissionSummaries(ctx context.Context, r *ojv1.ListSubmissionSummariesRequest) (*ojv1.ListSubmissionSummariesResponse, error) {
	return handleFake(f, ctx, "ListSubmissionSummaries", r, &ojv1.ListSubmissionSummariesResponse{})
}
func (f *fakeJudge) GetSubmissionDetail(ctx context.Context, r *ojv1.GetSubmissionDetailRequest) (*ojv1.GetSubmissionDetailResponse, error) {
	return handleFake(f, ctx, "GetSubmissionDetail", r, &ojv1.GetSubmissionDetailResponse{})
}
func (f *fakeJudge) RunCode(ctx context.Context, r *ojv1.RunCodeRequest) (*ojv1.RunCodeResponse, error) {
	return handleFake(f, ctx, "RunCode", r, &ojv1.RunCodeResponse{})
}
func (f *fakeJudge) AddProblem(ctx context.Context, r *ojv1.AddProblemRequest) (*ojv1.AddProblemResponse, error) {
	return handleFake(f, ctx, "AddProblem", r, &ojv1.AddProblemResponse{})
}
func (f *fakeJudge) EditProblem(ctx context.Context, r *ojv1.EditProblemRequest) (*ojv1.EditProblemResponse, error) {
	return handleFake(f, ctx, "EditProblem", r, &ojv1.EditProblemResponse{})
}
func (f *fakeJudge) RemoveProblem(ctx context.Context, r *ojv1.RemoveProblemRequest) (*ojv1.RemoveProblemResponse, error) {
	return handleFake(f, ctx, "RemoveProblem", r, &ojv1.RemoveProblemResponse{})
}
func (f *fakeJudge) ListProblemTestCases(ctx context.Context, r *ojv1.ListProblemTestCasesRequest) (*ojv1.ListProblemTestCasesResponse, error) {
	return handleFake(f, ctx, "ListProblemTestCases", r, &ojv1.ListProblemTestCasesResponse{})
}
func (f *fakeJudge) AddTestCase(ctx context.Context, r *ojv1.AddTestCaseRequest) (*ojv1.AddTestCaseResponse, error) {
	return handleFake(f, ctx, "AddTestCase", r, &ojv1.AddTestCaseResponse{})
}
func (f *fakeJudge) RemoveTestCase(ctx context.Context, r *ojv1.RemoveTestCaseRequest) (*ojv1.RemoveTestCaseResponse, error) {
	return handleFake(f, ctx, "RemoveTestCase", r, &ojv1.RemoveTestCaseResponse{})
}

// newGateway serves fake over bufconn and returns a gateway calling it.
func newGateway(t *testing.T, cfg Config) (*Gateway, *fakeJudge) {
	t.Helper()
	fake := &fakeJudge{resp: map[string]proto.Message{}}
	lis := bufconn.Listen(1 << 20)
	srv := grpc.NewServer()
	ojv1.RegisterJudgeServiceServer(srv, fake)
	go func() { _ = srv.Serve(lis) }()
	conn, err := grpc.NewClient("passthrough:///bufnet",
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) { return lis.DialContext(ctx) }),
		grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { conn.Close(); srv.Stop() })
	cfg.Client = ojv1.NewJudgeServiceClient(conn)
	if cfg.RateLimitPerMin == 0 {
		cfg.RateLimitPerMin, cfg.RateLimitBurst = 600, 100
	}
	return New(cfg), fake
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

func decodeError(t *testing.T, rec *httptest.ResponseRecorder) *ojv1.ErrorResponse {
	t.Helper()
	var e ojv1.ErrorResponse
	if err := protojson.Unmarshal(rec.Body.Bytes(), &e); err != nil {
		t.Fatalf("body is not an ErrorResponse: %v: %s", err, rec.Body)
	}
	var raw map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &raw)
	if _, ok := raw["details"]; !ok {
		t.Errorf("details must always be present: %s", rec.Body)
	}
	return &e
}

func TestRoutesBuildRequests(t *testing.T) {
	g, fake := newGateway(t, Config{AdminToken: "s3cret"})
	auth := map[string]string{"Authorization": "Bearer s3cret"}

	cases := []struct {
		method, path, body string
		hdr                map[string]string
		wantStatus         int
		wantRPC            string
		wantReq            proto.Message
	}{
		{"GET", "/api/v1/status", "", nil, 200, "GetStatus", &ojv1.GetStatusRequest{}},
		{"GET", "/api/v1/languages", "", nil, 200, "ListLanguages", &ojv1.ListLanguagesRequest{}},
		{"GET", "/api/v1/problems", "", nil, 200, "ListProblemSummaries", &ojv1.ListProblemSummariesRequest{}},
		{"GET", "/api/v1/problems/12", "", nil, 200, "GetProblemDetail", &ojv1.GetProblemDetailRequest{Id: 12}},
		{"POST", "/api/v1/submissions", `{"problemId":"1","language":"LANGUAGE_PYTHON","source":"print(1)","username":"ann"}`, nil,
			202, "Submit", &ojv1.SubmitRequest{ProblemId: 1, Language: ojv1.Language_LANGUAGE_PYTHON, Source: "print(1)", Username: "ann"}},
		{"GET", "/api/v1/submissions?problemId=3&username=ann&limit=5&offset=10", "", nil, 200, "ListSubmissionSummaries",
			&ojv1.ListSubmissionSummariesRequest{ProblemId: 3, Username: "ann", Limit: 5, Offset: 10}},
		{"GET", "/api/v1/submissions?problem_id=4", "", nil, 200, "ListSubmissionSummaries",
			&ojv1.ListSubmissionSummariesRequest{ProblemId: 4}},
		{"GET", "/api/v1/submissions/7", "", nil, 200, "GetSubmissionDetail", &ojv1.GetSubmissionDetailRequest{Id: 7}},
		{"POST", "/api/v1/run", `{"language":"LANGUAGE_C","source":"int main(){}","stdin":"x","problemId":2}`, nil,
			200, "RunCode", &ojv1.RunCodeRequest{Language: ojv1.Language_LANGUAGE_C, Source: "int main(){}", Stdin: "x", ProblemId: 2}},
		{"POST", "/api/v1/admin/problems", `{"slug":"a-b","title":"A","testCases":[{"input":"1","expectedOutput":"2","isSample":true}]}`, auth,
			201, "AddProblem", &ojv1.AddProblemRequest{Slug: "a-b", Title: "A", TestCases: []*ojv1.NewTestCase{{Input: "1", ExpectedOutput: "2", IsSample: true}}}},
		// The path id wins over a body id.
		{"PUT", "/api/v1/admin/problems/4", `{"id":"99","title":"T","difficulty":"DIFFICULTY_HARD"}`, auth,
			200, "EditProblem", &ojv1.EditProblemRequest{Id: 4, Title: "T", Difficulty: ojv1.Difficulty_DIFFICULTY_HARD}},
		{"DELETE", "/api/v1/admin/problems/4", "", auth, 204, "RemoveProblem", &ojv1.RemoveProblemRequest{Id: 4}},
		{"GET", "/api/v1/admin/problems/4/testcases", "", auth, 200, "ListProblemTestCases", &ojv1.ListProblemTestCasesRequest{ProblemId: 4}},
		{"POST", "/api/v1/admin/problems/4/testcases", `{"testCase":{"input":"i","expectedOutput":"o"}}`, auth,
			201, "AddTestCase", &ojv1.AddTestCaseRequest{ProblemId: 4, TestCase: &ojv1.NewTestCase{Input: "i", ExpectedOutput: "o"}}},
		{"DELETE", "/api/v1/admin/problems/4/testcases/9", "", auth, 204, "RemoveTestCase", &ojv1.RemoveTestCaseRequest{ProblemId: 4, Id: 9}},
	}
	for _, c := range cases {
		rec := call(g, c.method, c.path, c.body, c.hdr)
		method, req, _ := fake.last()
		if rec.Code != c.wantStatus || method != c.wantRPC || !proto.Equal(req, c.wantReq) {
			t.Errorf("%s %s -> %d %s(%v), want %d %s(%v); body %s",
				c.method, c.path, rec.Code, method, req, c.wantStatus, c.wantRPC, c.wantReq, rec.Body)
			continue
		}
		if c.wantStatus == http.StatusNoContent {
			if rec.Body.Len() != 0 {
				t.Errorf("%s %s: 204 must have no body, got %s", c.method, c.path, rec.Body)
			}
		} else if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
			t.Errorf("%s %s: content type %q", c.method, c.path, ct)
		}
	}
}

func TestResponseJSONShape(t *testing.T) {
	g, fake := newGateway(t, Config{})
	fake.resp["GetSubmissionDetail"] = &ojv1.GetSubmissionDetailResponse{Submission: &ojv1.Submission{
		Id: 7, ProblemId: 3, Language: ojv1.Language_LANGUAGE_PYTHON,
		Status: ojv1.SubmissionStatus_SUBMISSION_STATUS_FINISHED, Verdict: ojv1.Verdict_VERDICT_ACCEPTED,
		CreateTime: timestamppb.New(time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC)),
	}}
	rec := call(g, "GET", "/api/v1/submissions/7", "", nil)
	var body struct {
		Submission map[string]any `json:"submission"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil || rec.Code != 200 {
		t.Fatalf("%d %s (%v)", rec.Code, rec.Body, err)
	}
	s := body.Submission
	want := map[string]any{
		"id": "7", "problemId": "3", "language": "LANGUAGE_PYTHON",
		"status": "SUBMISSION_STATUS_FINISHED", "verdict": "VERDICT_ACCEPTED",
		"username": "", "timeMs": float64(0), "results": []any{},
		"createTime": "2026-01-02T03:04:05Z", "updateTime": nil,
	}
	for k, v := range want {
		got, ok := s[k]
		if !ok {
			t.Errorf("missing field %q in %s", k, rec.Body)
			continue
		}
		gb, _ := json.Marshal(got)
		wb, _ := json.Marshal(v)
		if string(gb) != string(wb) {
			t.Errorf("%s = %s, want %s", k, gb, wb)
		}
	}
	if _, ok := s["problem_id"]; ok {
		t.Errorf("snake_case field emitted: %s", rec.Body)
	}
}

func TestBadRequests(t *testing.T) {
	g, fake := newGateway(t, Config{AdminToken: "s3cret"})
	auth := map[string]string{"Authorization": "Bearer s3cret"}
	cases := []struct {
		method, path, body string
		hdr                map[string]string
	}{
		{"POST", "/api/v1/submissions", `{"problemId":"1","bogus":true}`, nil},
		{"POST", "/api/v1/submissions", `{"problemId":`, nil},
		{"POST", "/api/v1/submissions", `{"language":"COBOL"}`, nil},
		{"POST", "/api/v1/run", `[]`, nil},
		{"GET", "/api/v1/problems/abc", "", nil},
		{"GET", "/api/v1/problems/0", "", nil},
		{"GET", "/api/v1/problems/-1", "", nil},
		{"GET", "/api/v1/problems/99999999999999999999", "", nil},
		{"GET", "/api/v1/submissions?problemId=x", "", nil},
		{"GET", "/api/v1/submissions?limit=-1", "", nil},
		{"GET", "/api/v1/submissions?offset=1e3", "", nil},
		{"PUT", "/api/v1/admin/problems/x", `{}`, auth},
		{"DELETE", "/api/v1/admin/problems/4/testcases/0", "", auth},
	}
	for _, c := range cases {
		rec := call(g, c.method, c.path, c.body, c.hdr)
		if rec.Code != http.StatusBadRequest {
			t.Errorf("%s %s %s: got %d %s", c.method, c.path, c.body, rec.Code, rec.Body)
			continue
		}
		if e := decodeError(t, rec); e.Error == "" {
			t.Errorf("%s %s: empty error message", c.method, c.path)
		}
	}
	if method, _, _ := fake.last(); method != "" {
		t.Fatalf("invalid requests must not reach the midlayer, got %s", method)
	}

	rec := call(g, "POST", "/api/v1/submissions", `{"bogus":1}`, nil)
	if e := decodeError(t, rec); len(e.Details) == 0 || !strings.Contains(e.Details[0], "bogus") {
		t.Errorf("unknown field should be named in details: %s", rec.Body)
	}
}

func TestUnknownRoutes(t *testing.T) {
	g, fake := newGateway(t, Config{})
	for _, p := range []string{"/api/v1/readyz", "/problems", "/api/v2/problems"} {
		if rec := call(g, "GET", p, "", nil); rec.Code != 404 {
			t.Errorf("%s: got %d", p, rec.Code)
		}
	}
	// Admin-only mutation is not exposed publicly.
	if rec := call(g, "DELETE", "/api/v1/problems/1", "", nil); rec.Code != 405 && rec.Code != 404 {
		t.Errorf("public delete: got %d", rec.Code)
	}
	if method, _, _ := fake.last(); method != "" {
		t.Fatalf("nothing should reach the midlayer, got %s", method)
	}
}

func TestGRPCErrorMapping(t *testing.T) {
	g, fake := newGateway(t, Config{})
	cases := []struct {
		code       codes.Code
		wantStatus int
		wantMsg    string
	}{
		{codes.InvalidArgument, 422, "source: must not be empty"},
		{codes.NotFound, 404, "source: must not be empty"},
		{codes.AlreadyExists, 409, "source: must not be empty"},
		{codes.FailedPrecondition, 409, "source: must not be empty"},
		{codes.ResourceExhausted, 429, "source: must not be empty"},
		{codes.DeadlineExceeded, 504, "upstream timed out"},
		{codes.Unavailable, 503, "service unavailable"},
		{codes.Internal, 502, "upstream error"},
		{codes.Unknown, 502, "upstream error"},
		{codes.PermissionDenied, 502, "upstream error"},
	}
	for _, c := range cases {
		fake.mu.Lock()
		fake.err = status.Error(c.code, "source: must not be empty")
		fake.mu.Unlock()
		rec := call(g, "POST", "/api/v1/submissions", `{}`, nil)
		e := decodeError(t, rec)
		if rec.Code != c.wantStatus || e.Error != c.wantMsg {
			t.Errorf("%s -> %d %q, want %d %q", c.code, rec.Code, e.Error, c.wantStatus, c.wantMsg)
		}
	}
}

func TestDeadlines(t *testing.T) {
	g, fake := newGateway(t, Config{UpstreamTimeout: 50 * time.Millisecond, RunTimeout: 400 * time.Millisecond})
	fake.block = true

	start := time.Now()
	if rec := call(g, "GET", "/api/v1/problems", "", nil); rec.Code != http.StatusGatewayTimeout {
		t.Fatalf("got %d %s", rec.Code, rec.Body)
	}
	if d := time.Since(start); d > 300*time.Millisecond {
		t.Fatalf("upstream deadline not applied: took %s", d)
	}

	// RunCode gets its own, longer deadline.
	start = time.Now()
	if rec := call(g, "POST", "/api/v1/run", "{}", nil); rec.Code != http.StatusGatewayTimeout {
		t.Fatalf("got %d %s", rec.Code, rec.Body)
	}
	if d := time.Since(start); d < 350*time.Millisecond || d > 2*time.Second {
		t.Fatalf("run deadline not applied: took %s", d)
	}
}

func TestMetadataForwarding(t *testing.T) {
	g, fake := newGateway(t, Config{AdminToken: "s3cret"})
	call(g, "GET", "/api/v1/admin/problems/1/testcases", "", map[string]string{
		"Authorization": "Bearer s3cret", "Cookie": "session=abc", "X-Request-ID": "req-42",
	})
	_, _, md := fake.last()
	if got := md.Get("x-request-id"); len(got) != 1 || got[0] != "req-42" {
		t.Errorf("x-request-id = %v", got)
	}
	if len(md.Get("authorization")) != 0 || len(md.Get("cookie")) != 0 {
		t.Errorf("credentials leaked upstream: %v", md)
	}
}

func TestAdminAuth(t *testing.T) {
	g, fake := newGateway(t, Config{AdminToken: "s3cret"})
	for _, h := range []map[string]string{nil, {"Authorization": "Bearer wrong"}} {
		rec := call(g, "POST", "/api/v1/admin/problems", "{}", h)
		if rec.Code != 401 {
			t.Fatalf("bad token: %d", rec.Code)
		}
		decodeError(t, rec)
	}
	if method, _, _ := fake.last(); method != "" {
		t.Fatalf("unauthenticated request reached the midlayer: %s", method)
	}
	rec := call(g, "GET", "/api/v1/admin/verify", "", map[string]string{"Authorization": "Bearer s3cret"})
	var body map[string]bool
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if rec.Code != 200 || !body["admin"] {
		t.Fatalf("verify: %d %s", rec.Code, rec.Body)
	}

	off, _ := newGateway(t, Config{})
	if rec := call(off, "GET", "/api/v1/admin/verify", "", map[string]string{"Authorization": "Bearer "}); rec.Code != 403 {
		t.Fatalf("admin disabled: %d", rec.Code)
	}
}

func TestSubmissionRateLimited(t *testing.T) {
	g, _ := newGateway(t, Config{RateLimitPerMin: 1, RateLimitBurst: 2})
	codes := []int{}
	for range 3 {
		codes = append(codes, call(g, "POST", "/api/v1/submissions", "{}", nil).Code)
	}
	if codes[0] != 202 || codes[1] != 202 || codes[2] != 429 {
		t.Fatalf("codes = %v", codes)
	}
	rec := call(g, "POST", "/api/v1/run", "{}", nil)
	if rec.Code != 429 || rec.Header().Get("Retry-After") == "" {
		t.Fatalf("run shares the limiter: %d %v", rec.Code, rec.Header())
	}
	decodeError(t, rec)
	// Reads are never rate limited.
	if rec := call(g, "GET", "/api/v1/problems", "", nil); rec.Code != 200 {
		t.Fatalf("read was limited: %d", rec.Code)
	}
}

func TestBodyTooLarge(t *testing.T) {
	g, _ := newGateway(t, Config{})
	big := `{"source":"` + strings.Repeat("a", maxSubmissionBody) + `"}`
	// Chunked body (unknown length) is cut off by MaxBytesReader.
	req := httptest.NewRequest("POST", "/api/v1/submissions", strings.NewReader(big))
	req.ContentLength = -1
	rec := httptest.NewRecorder()
	g.ServeHTTP(rec, req)
	if rec.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf("got %d", rec.Code)
	}
}

func TestUpstreamDown(t *testing.T) {
	conn, err := grpc.NewClient("passthrough:///down",
		grpc.WithContextDialer(func(context.Context, string) (net.Conn, error) { return nil, net.ErrClosed }),
		grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	g := New(Config{Client: ojv1.NewJudgeServiceClient(conn), UpstreamTimeout: 2 * time.Second})
	rec := call(g, "GET", "/api/v1/problems", "", nil)
	if rec.Code != http.StatusServiceUnavailable || decodeError(t, rec).Error != "service unavailable" {
		t.Fatalf("got %d %s", rec.Code, rec.Body)
	}
	// Liveness never depends on the midlayer.
	if rec := call(g, "GET", "/healthz", "", nil); rec.Code != 200 {
		t.Fatalf("healthz %d", rec.Code)
	}
}

// Package grpcapi implements oj.v1.DaoService on top of store.Store. It only
// translates: it validates and converts requests into store calls and maps
// results and errors back to protobuf / gRPC status codes. All database
// access goes through the store package.
package grpcapi

import (
	"context"
	"regexp"
	"strings"

	ojv1 "github.com/online-judge/online-judge/dao/internal/gen/oj/v1"
	"github.com/online-judge/online-judge/dao/internal/store"
)

// Defaults applied when a problem's limits are left at zero.
const (
	DefaultTimeLimitMs   = 2000
	DefaultMemoryLimitMb = 256
	// DefaultUsername is stored when a submission has no username.
	DefaultUsername = "anonymous"
	// MaxListLimit is the largest ListSubmissions page.
	MaxListLimit = 500
)

var slugRE = regexp.MustCompile(`^[a-z0-9]+(?:-[a-z0-9]+)*$`)

// Server implements ojv1.DaoServiceServer.
type Server struct {
	ojv1.UnimplementedDaoServiceServer
	store store.Store
}

// New returns a DaoService backed by st.
func New(st store.Store) *Server { return &Server{store: st} }

// ---------- problems ----------

func (s *Server) ListProblems(ctx context.Context, _ *ojv1.ListProblemsRequest) (*ojv1.ListProblemsResponse, error) {
	ps, err := s.store.ListProblems(ctx)
	if err != nil {
		return nil, storeError(ctx, err)
	}
	out := make([]*ojv1.Problem, len(ps))
	for i, p := range ps {
		out[i] = problemToProto(p)
	}
	return &ojv1.ListProblemsResponse{Problems: out}, nil
}

func (s *Server) GetProblem(ctx context.Context, req *ojv1.GetProblemRequest) (*ojv1.GetProblemResponse, error) {
	if req.GetId() <= 0 {
		return nil, invalidArgf("id is required")
	}
	p, err := s.store.GetProblem(ctx, req.GetId())
	if err != nil {
		return nil, storeError(ctx, err)
	}
	return &ojv1.GetProblemResponse{Problem: problemToProto(p)}, nil
}

func (s *Server) CreateProblem(ctx context.Context, req *ojv1.CreateProblemRequest) (*ojv1.CreateProblemResponse, error) {
	p, err := problemFromProto(req.GetProblem())
	if err != nil {
		return nil, err
	}
	tcs := make([]store.TestCase, len(req.GetTestCases()))
	for i, tc := range req.GetTestCases() {
		if tc == nil {
			return nil, invalidArgf("test_cases[%d] is empty", i)
		}
		tcs[i] = store.TestCase{Input: tc.GetInput(), ExpectedOutput: tc.GetExpectedOutput(), IsSample: tc.GetIsSample()}
	}
	created, createdTCs, err := s.store.CreateProblem(ctx, p, tcs)
	if err != nil {
		return nil, storeError(ctx, err)
	}
	return &ojv1.CreateProblemResponse{Problem: problemToProto(created), TestCases: testCasesToProto(createdTCs)}, nil
}

func (s *Server) UpdateProblem(ctx context.Context, req *ojv1.UpdateProblemRequest) (*ojv1.UpdateProblemResponse, error) {
	if req.GetProblem().GetId() <= 0 {
		return nil, invalidArgf("problem.id is required")
	}
	p, err := problemFromProto(req.GetProblem())
	if err != nil {
		return nil, err
	}
	p.ID = req.GetProblem().GetId()
	updated, err := s.store.UpdateProblem(ctx, p)
	if err != nil {
		return nil, storeError(ctx, err)
	}
	return &ojv1.UpdateProblemResponse{Problem: problemToProto(updated)}, nil
}

func (s *Server) DeleteProblem(ctx context.Context, req *ojv1.DeleteProblemRequest) (*ojv1.DeleteProblemResponse, error) {
	if req.GetId() <= 0 {
		return nil, invalidArgf("id is required")
	}
	if err := s.store.DeleteProblem(ctx, req.GetId()); err != nil {
		return nil, storeError(ctx, err)
	}
	return &ojv1.DeleteProblemResponse{}, nil
}

// problemFromProto validates the writable fields of a problem (id and
// create_time are ignored).
func problemFromProto(p *ojv1.Problem) (store.Problem, error) {
	if p == nil {
		return store.Problem{}, invalidArgf("problem is required")
	}
	out := store.Problem{
		Slug:          strings.TrimSpace(p.GetSlug()),
		Title:         strings.TrimSpace(p.GetTitle()),
		Statement:     p.GetStatement(),
		TimeLimitMs:   int(p.GetTimeLimitMs()),
		MemoryLimitMb: int(p.GetMemoryLimitMb()),
	}
	if len(out.Slug) > 64 || !slugRE.MatchString(out.Slug) {
		return store.Problem{}, invalidArgf("problem.slug must be lowercase kebab-case, 1-64 characters")
	}
	if out.Title == "" {
		return store.Problem{}, invalidArgf("problem.title is required")
	}
	d, ok := difficultyFromProto(p.GetDifficulty())
	if !ok {
		return store.Problem{}, invalidArgf("problem.difficulty: unsupported value %v", p.GetDifficulty())
	}
	out.Difficulty = d
	if out.TimeLimitMs < 0 || out.MemoryLimitMb < 0 {
		return store.Problem{}, invalidArgf("problem limits must not be negative")
	}
	if out.TimeLimitMs == 0 {
		out.TimeLimitMs = DefaultTimeLimitMs
	}
	if out.MemoryLimitMb == 0 {
		out.MemoryLimitMb = DefaultMemoryLimitMb
	}
	return out, nil
}

// ---------- test cases ----------

func (s *Server) ListTestCases(ctx context.Context, req *ojv1.ListTestCasesRequest) (*ojv1.ListTestCasesResponse, error) {
	if req.GetProblemId() <= 0 {
		return nil, invalidArgf("problem_id is required")
	}
	tcs, err := s.store.ListTestCases(ctx, req.GetProblemId(), req.GetSamplesOnly())
	if err != nil {
		return nil, storeError(ctx, err)
	}
	return &ojv1.ListTestCasesResponse{TestCases: testCasesToProto(tcs)}, nil
}

func (s *Server) CreateTestCase(ctx context.Context, req *ojv1.CreateTestCaseRequest) (*ojv1.CreateTestCaseResponse, error) {
	tc := req.GetTestCase()
	if tc == nil {
		return nil, invalidArgf("test_case is required")
	}
	if tc.GetProblemId() <= 0 {
		return nil, invalidArgf("test_case.problem_id is required")
	}
	created, err := s.store.CreateTestCase(ctx, store.TestCase{
		ProblemID:      tc.GetProblemId(),
		Input:          tc.GetInput(),
		ExpectedOutput: tc.GetExpectedOutput(),
		IsSample:       tc.GetIsSample(),
	})
	if err != nil {
		return nil, storeError(ctx, err)
	}
	return &ojv1.CreateTestCaseResponse{TestCase: testCaseToProto(created)}, nil
}

func (s *Server) DeleteTestCase(ctx context.Context, req *ojv1.DeleteTestCaseRequest) (*ojv1.DeleteTestCaseResponse, error) {
	if req.GetProblemId() <= 0 || req.GetId() <= 0 {
		return nil, invalidArgf("problem_id and id are required")
	}
	if err := s.store.DeleteTestCase(ctx, req.GetProblemId(), req.GetId()); err != nil {
		return nil, storeError(ctx, err)
	}
	return &ojv1.DeleteTestCaseResponse{}, nil
}

// ---------- submissions ----------

func (s *Server) CreateSubmission(ctx context.Context, req *ojv1.CreateSubmissionRequest) (*ojv1.CreateSubmissionResponse, error) {
	in := req.GetSubmission()
	if in == nil {
		return nil, invalidArgf("submission is required")
	}
	if in.GetProblemId() <= 0 {
		return nil, invalidArgf("submission.problem_id is required")
	}
	lang, ok := languageFromProto(in.GetLanguage())
	if !ok {
		return nil, invalidArgf("submission.language: unsupported value %v", in.GetLanguage())
	}
	if in.GetSource() == "" {
		return nil, invalidArgf("submission.source is required")
	}
	username := strings.TrimSpace(in.GetUsername())
	if username == "" {
		username = DefaultUsername
	}
	sub, err := s.store.CreateSubmission(ctx, store.Submission{
		ProblemID: in.GetProblemId(),
		Username:  username,
		Language:  lang,
		Source:    in.GetSource(),
	})
	if err != nil {
		return nil, storeError(ctx, err)
	}
	return &ojv1.CreateSubmissionResponse{Submission: submissionToProto(sub)}, nil
}

func (s *Server) GetSubmission(ctx context.Context, req *ojv1.GetSubmissionRequest) (*ojv1.GetSubmissionResponse, error) {
	if req.GetId() <= 0 {
		return nil, invalidArgf("id is required")
	}
	sub, err := s.store.GetSubmission(ctx, req.GetId())
	if err != nil {
		return nil, storeError(ctx, err)
	}
	return &ojv1.GetSubmissionResponse{Submission: submissionToProto(sub)}, nil
}

func (s *Server) ListSubmissions(ctx context.Context, req *ojv1.ListSubmissionsRequest) (*ojv1.ListSubmissionsResponse, error) {
	f := store.SubmissionFilter{
		ProblemID: req.GetProblemId(),
		Username:  req.GetUsername(),
		Limit:     int(req.GetLimit()),
		Offset:    int(req.GetOffset()),
	}
	if f.ProblemID < 0 {
		return nil, invalidArgf("problem_id must not be negative")
	}
	if f.Limit < 0 || f.Limit > MaxListLimit {
		return nil, invalidArgf("limit must be between 1 and %d (0 means %d)", MaxListLimit, store.DefaultListLimit)
	}
	if f.Offset < 0 {
		return nil, invalidArgf("offset must not be negative")
	}
	for i, st := range req.GetStatuses() {
		v, ok := statusFromProto(st)
		if !ok {
			return nil, invalidArgf("statuses[%d]: unsupported value %v", i, st)
		}
		f.Statuses = append(f.Statuses, v)
	}
	if ub := req.GetUpdatedBefore(); ub != nil {
		if err := ub.CheckValid(); err != nil {
			return nil, invalidArgf("updated_before: %v", err)
		}
		f.UpdatedBefore = ub.AsTime()
	}
	subs, err := s.store.ListSubmissions(ctx, f)
	if err != nil {
		return nil, storeError(ctx, err)
	}
	out := make([]*ojv1.Submission, len(subs))
	for i, sub := range subs {
		out[i] = submissionToProto(sub)
	}
	return &ojv1.ListSubmissionsResponse{Submissions: out}, nil
}

func (s *Server) UpdateSubmission(ctx context.Context, req *ojv1.UpdateSubmissionRequest) (*ojv1.UpdateSubmissionResponse, error) {
	if req.GetId() <= 0 {
		return nil, invalidArgf("id is required")
	}
	var u store.SubmissionUpdate
	if req.Status != nil {
		v, ok := statusFromProto(req.GetStatus())
		if !ok {
			return nil, invalidArgf("status: unsupported value %v", req.GetStatus())
		}
		u.Status = &v
	}
	if req.Verdict != nil {
		v, ok := verdictFromProto(req.GetVerdict())
		if !ok {
			return nil, invalidArgf("verdict: unsupported value %v", req.GetVerdict())
		}
		u.Verdict = &v
	}
	if req.Passed != nil {
		v := int(req.GetPassed())
		u.Passed = &v
	}
	if req.Total != nil {
		v := int(req.GetTotal())
		u.Total = &v
	}
	if req.TimeMs != nil {
		v := int(req.GetTimeMs())
		u.TimeMs = &v
	}
	if req.Message != nil {
		v := req.GetMessage()
		u.Message = &v
	}
	if req.Results != nil {
		rs := make([]store.TestResult, len(req.GetResults().GetResults()))
		for i, r := range req.GetResults().GetResults() {
			v, ok := testResultFromProto(r)
			if !ok {
				return nil, invalidArgf("results[%d].verdict: unsupported value %v", i, r.GetVerdict())
			}
			rs[i] = v
		}
		u.Results = &rs
	}
	for i, st := range req.GetExpectedStatuses() {
		v, ok := statusFromProto(st)
		if !ok {
			return nil, invalidArgf("expected_statuses[%d]: unsupported value %v", i, st)
		}
		u.ExpectedStatuses = append(u.ExpectedStatuses, v)
	}
	sub, err := s.store.UpdateSubmission(ctx, req.GetId(), u)
	if err != nil {
		return nil, storeError(ctx, err)
	}
	return &ojv1.UpdateSubmissionResponse{Submission: submissionToProto(sub)}, nil
}

package grpcapi_test

import (
	"context"
	"net"
	"strings"
	"testing"
	"time"

	ojv1 "github.com/online-judge/oj-dao/internal/gen/oj/v1"
	"github.com/online-judge/oj-dao/internal/grpcapi"
	"github.com/online-judge/oj-dao/internal/store"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// Functional tests: the real gRPC server (interceptors, limits, health)
// over an in-process bufconn listener, backed by the memory store.

type env struct {
	dao    ojv1.DaoServiceClient
	health healthpb.HealthClient
}

func newEnv(t *testing.T) env {
	t.Helper()
	lis := bufconn.Listen(1 << 20)
	hs := health.NewServer()
	st := store.NewMemory()
	grpcapi.NewHealthChecker(st, hs, time.Minute).CheckOnce(context.Background())
	srv := grpcapi.NewGRPCServer(st, hs)
	go func() { _ = srv.Serve(lis) }()
	t.Cleanup(srv.Stop)

	conn, err := grpc.NewClient("passthrough:///bufnet",
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) { return lis.DialContext(ctx) }),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithDefaultCallOptions(
			grpc.MaxCallRecvMsgSize(grpcapi.MaxMessageSize),
			grpc.MaxCallSendMsgSize(grpcapi.MaxMessageSize)),
	)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = conn.Close() })
	return env{dao: ojv1.NewDaoServiceClient(conn), health: healthpb.NewHealthClient(conn)}
}

func ctx(t *testing.T) context.Context {
	t.Helper()
	c, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	t.Cleanup(cancel)
	return c
}

func wantCode(t *testing.T, err error, want codes.Code) {
	t.Helper()
	if status.Code(err) != want {
		t.Fatalf("code = %v, want %v (err=%v)", status.Code(err), want, err)
	}
}

func newProblem(t *testing.T, e env, slug string, tcs ...*ojv1.TestCase) *ojv1.CreateProblemResponse {
	t.Helper()
	resp, err := e.dao.CreateProblem(ctx(t), &ojv1.CreateProblemRequest{
		Problem:   &ojv1.Problem{Slug: slug, Title: "T " + slug, Statement: "s", Difficulty: ojv1.Difficulty_DIFFICULTY_EASY},
		TestCases: tcs,
	})
	if err != nil {
		t.Fatal(err)
	}
	return resp
}

func newSubmission(t *testing.T, e env, problemID int64, user string) *ojv1.Submission {
	t.Helper()
	resp, err := e.dao.CreateSubmission(ctx(t), &ojv1.CreateSubmissionRequest{Submission: &ojv1.Submission{
		ProblemId: problemID, Username: user, Language: ojv1.Language_LANGUAGE_PYTHON, Source: "print(1)",
	}})
	if err != nil {
		t.Fatal(err)
	}
	return resp.GetSubmission()
}

func TestHealth(t *testing.T) {
	e := newEnv(t)
	for _, svc := range []string{"", "oj.v1.DaoService"} {
		resp, err := e.health.Check(ctx(t), &healthpb.HealthCheckRequest{Service: svc})
		if err != nil || resp.GetStatus() != healthpb.HealthCheckResponse_SERVING {
			t.Fatalf("%q: %v %v", svc, resp, err)
		}
	}
	_, err := e.health.Check(ctx(t), &healthpb.HealthCheckRequest{Service: "nope"})
	wantCode(t, err, codes.NotFound)
}

func TestProblemCRUD(t *testing.T) {
	e := newEnv(t)
	created := newProblem(t, e, "sum")
	p := created.GetProblem()
	if p.GetId() == 0 || p.GetTimeLimitMs() != 2000 || p.GetMemoryLimitMb() != 256 ||
		p.GetDifficulty() != ojv1.Difficulty_DIFFICULTY_EASY || p.GetCreateTime() == nil {
		t.Fatalf("defaults not applied: %v", p)
	}

	_, err := e.dao.CreateProblem(ctx(t), &ojv1.CreateProblemRequest{Problem: &ojv1.Problem{
		Slug: "sum", Title: "x", Difficulty: ojv1.Difficulty_DIFFICULTY_EASY}})
	wantCode(t, err, codes.AlreadyExists)
	_, err = e.dao.CreateProblem(ctx(t), &ojv1.CreateProblemRequest{Problem: &ojv1.Problem{
		Slug: "y", Difficulty: ojv1.Difficulty_DIFFICULTY_EASY}})
	wantCode(t, err, codes.InvalidArgument)
	_, err = e.dao.CreateProblem(ctx(t), &ojv1.CreateProblemRequest{Problem: &ojv1.Problem{Slug: "y", Title: "y"}})
	wantCode(t, err, codes.InvalidArgument) // DIFFICULTY_UNSPECIFIED
	_, err = e.dao.CreateProblem(ctx(t), &ojv1.CreateProblemRequest{})
	wantCode(t, err, codes.InvalidArgument)

	upd, err := e.dao.UpdateProblem(ctx(t), &ojv1.UpdateProblemRequest{Problem: &ojv1.Problem{
		Id: p.GetId(), Slug: "sum", Title: "Sum!", Difficulty: ojv1.Difficulty_DIFFICULTY_HARD, TimeLimitMs: 500,
	}})
	if err != nil {
		t.Fatal(err)
	}
	if got := upd.GetProblem(); got.GetTitle() != "Sum!" || got.GetTimeLimitMs() != 500 ||
		got.GetDifficulty() != ojv1.Difficulty_DIFFICULTY_HARD || !proto.Equal(got.GetCreateTime(), p.GetCreateTime()) {
		t.Fatalf("update not applied: %v", got)
	}
	_, err = e.dao.UpdateProblem(ctx(t), &ojv1.UpdateProblemRequest{Problem: &ojv1.Problem{
		Id: 999, Slug: "zz", Title: "z", Difficulty: ojv1.Difficulty_DIFFICULTY_EASY}})
	wantCode(t, err, codes.NotFound)
	_, err = e.dao.UpdateProblem(ctx(t), &ojv1.UpdateProblemRequest{Problem: &ojv1.Problem{
		Slug: "zz", Title: "z", Difficulty: ojv1.Difficulty_DIFFICULTY_EASY}})
	wantCode(t, err, codes.InvalidArgument)
	newProblem(t, e, "other")
	_, err = e.dao.UpdateProblem(ctx(t), &ojv1.UpdateProblemRequest{Problem: &ojv1.Problem{
		Id: p.GetId(), Slug: "other", Title: "z", Difficulty: ojv1.Difficulty_DIFFICULTY_EASY}})
	wantCode(t, err, codes.AlreadyExists)

	list, err := e.dao.ListProblems(ctx(t), &ojv1.ListProblemsRequest{})
	if err != nil || len(list.GetProblems()) != 2 || list.GetProblems()[0].GetSlug() != "sum" {
		t.Fatalf("list: %v %v", list, err)
	}

	got, err := e.dao.GetProblem(ctx(t), &ojv1.GetProblemRequest{Id: p.GetId()})
	if err != nil || got.GetProblem().GetTitle() != "Sum!" {
		t.Fatalf("get: %v %v", got, err)
	}
	_, err = e.dao.DeleteProblem(ctx(t), &ojv1.DeleteProblemRequest{Id: p.GetId()})
	if err != nil {
		t.Fatal(err)
	}
	_, err = e.dao.GetProblem(ctx(t), &ojv1.GetProblemRequest{Id: p.GetId()})
	wantCode(t, err, codes.NotFound)
	_, err = e.dao.DeleteProblem(ctx(t), &ojv1.DeleteProblemRequest{Id: p.GetId()})
	wantCode(t, err, codes.NotFound)
	_, err = e.dao.GetProblem(ctx(t), &ojv1.GetProblemRequest{})
	wantCode(t, err, codes.InvalidArgument)
}

func TestTestCases(t *testing.T) {
	e := newEnv(t)
	created := newProblem(t, e, "tc",
		&ojv1.TestCase{Input: "1", ExpectedOutput: "1", IsSample: true, Ordinal: 9, Id: 5, ProblemId: 77},
		&ojv1.TestCase{Input: "2", ExpectedOutput: "4"},
	)
	pid := created.GetProblem().GetId()
	if len(created.GetTestCases()) != 2 {
		t.Fatalf("want 2 test cases: %v", created)
	}
	for i, tc := range created.GetTestCases() {
		if tc.GetOrdinal() != int32(i+1) || tc.GetProblemId() != pid || tc.GetId() == 0 {
			t.Fatalf("test case %d: %v", i, tc)
		}
	}

	added, err := e.dao.CreateTestCase(ctx(t), &ojv1.CreateTestCaseRequest{TestCase: &ojv1.TestCase{
		ProblemId: pid, Input: "3", ExpectedOutput: "9", Ordinal: 1}})
	if err != nil || added.GetTestCase().GetOrdinal() != 3 {
		t.Fatalf("append: %v %v", added, err)
	}

	all, err := e.dao.ListTestCases(ctx(t), &ojv1.ListTestCasesRequest{ProblemId: pid})
	if err != nil || len(all.GetTestCases()) != 3 || all.GetTestCases()[2].GetInput() != "3" {
		t.Fatalf("list: %v %v", all, err)
	}
	samples, err := e.dao.ListTestCases(ctx(t), &ojv1.ListTestCasesRequest{ProblemId: pid, SamplesOnly: true})
	if err != nil || len(samples.GetTestCases()) != 1 || !samples.GetTestCases()[0].GetIsSample() {
		t.Fatalf("samples: %v %v", samples, err)
	}

	tcID := added.GetTestCase().GetId()
	_, err = e.dao.DeleteTestCase(ctx(t), &ojv1.DeleteTestCaseRequest{ProblemId: pid, Id: tcID})
	if err != nil {
		t.Fatal(err)
	}
	_, err = e.dao.DeleteTestCase(ctx(t), &ojv1.DeleteTestCaseRequest{ProblemId: pid, Id: tcID})
	wantCode(t, err, codes.NotFound)
	_, err = e.dao.CreateTestCase(ctx(t), &ojv1.CreateTestCaseRequest{TestCase: &ojv1.TestCase{ProblemId: 999, Input: "1"}})
	wantCode(t, err, codes.NotFound)
	_, err = e.dao.CreateTestCase(ctx(t), &ojv1.CreateTestCaseRequest{})
	wantCode(t, err, codes.InvalidArgument)
	_, err = e.dao.ListTestCases(ctx(t), &ojv1.ListTestCasesRequest{ProblemId: 999})
	wantCode(t, err, codes.NotFound)
	_, err = e.dao.ListTestCases(ctx(t), &ojv1.ListTestCasesRequest{})
	wantCode(t, err, codes.InvalidArgument)
	_, err = e.dao.DeleteTestCase(ctx(t), &ojv1.DeleteTestCaseRequest{ProblemId: pid})
	wantCode(t, err, codes.InvalidArgument)
}

func TestLargeTestData(t *testing.T) {
	e := newEnv(t)
	big := strings.Repeat("1234567\n", 3<<20) // 24 MiB, above gRPC's 4 MiB default
	created := newProblem(t, e, "big", &ojv1.TestCase{Input: big, ExpectedOutput: "ok"})
	list, err := e.dao.ListTestCases(ctx(t), &ojv1.ListTestCasesRequest{ProblemId: created.GetProblem().GetId()})
	if err != nil || len(list.GetTestCases()) != 1 || len(list.GetTestCases()[0].GetInput()) != len(big) {
		t.Fatalf("big test case: %v", err)
	}
}

func TestSubmissions(t *testing.T) {
	e := newEnv(t)
	pid := newProblem(t, e, "subs").GetProblem().GetId()

	_, err := e.dao.CreateSubmission(ctx(t), &ojv1.CreateSubmissionRequest{Submission: &ojv1.Submission{
		ProblemId: pid, Source: "x"}})
	wantCode(t, err, codes.InvalidArgument) // LANGUAGE_UNSPECIFIED
	_, err = e.dao.CreateSubmission(ctx(t), &ojv1.CreateSubmissionRequest{Submission: &ojv1.Submission{
		ProblemId: pid, Language: ojv1.Language_LANGUAGE_C}})
	wantCode(t, err, codes.InvalidArgument) // no source
	_, err = e.dao.CreateSubmission(ctx(t), &ojv1.CreateSubmissionRequest{Submission: &ojv1.Submission{
		ProblemId: 999, Language: ojv1.Language_LANGUAGE_PYTHON, Source: "x"}})
	wantCode(t, err, codes.NotFound)

	resp, err := e.dao.CreateSubmission(ctx(t), &ojv1.CreateSubmissionRequest{Submission: &ojv1.Submission{
		ProblemId: pid, Language: ojv1.Language_LANGUAGE_PYTHON, Source: "print(1)",
		Status: ojv1.SubmissionStatus_SUBMISSION_STATUS_FINISHED, Verdict: ojv1.Verdict_VERDICT_ACCEPTED, Passed: 5,
	}})
	if err != nil {
		t.Fatal(err)
	}
	sub := resp.GetSubmission()
	if sub.GetStatus() != ojv1.SubmissionStatus_SUBMISSION_STATUS_PENDING || sub.GetVerdict() != ojv1.Verdict_VERDICT_UNSPECIFIED ||
		sub.GetPassed() != 0 || sub.GetUsername() != "anonymous" || len(sub.GetResults()) != 0 ||
		sub.GetCreateTime() == nil || !proto.Equal(sub.GetCreateTime(), sub.GetUpdateTime()) {
		t.Fatalf("unexpected defaults: %v", sub)
	}
	time.Sleep(2 * time.Millisecond)
	bob := newSubmission(t, e, pid, "bob")

	upd, err := e.dao.UpdateSubmission(ctx(t), &ojv1.UpdateSubmissionRequest{
		Id:      sub.GetId(),
		Status:  ojv1.SubmissionStatus_SUBMISSION_STATUS_FINISHED.Enum(),
		Verdict: ojv1.Verdict_VERDICT_ACCEPTED.Enum(),
		Passed:  proto.Int32(3), Total: proto.Int32(3), TimeMs: proto.Int32(40), Message: proto.String("Accepted"),
		Results: &ojv1.TestResults{Results: []*ojv1.TestResult{
			{Test: 1, Verdict: ojv1.Verdict_VERDICT_ACCEPTED, TimeMs: 12, MemoryKb: 9000, Sample: true},
		}},
	})
	if err != nil {
		t.Fatal(err)
	}
	u := upd.GetSubmission()
	if u.GetVerdict() != ojv1.Verdict_VERDICT_ACCEPTED || u.GetPassed() != 3 || u.GetTimeMs() != 40 ||
		u.GetMessage() != "Accepted" || u.GetLanguage() != ojv1.Language_LANGUAGE_PYTHON || u.GetSource() != "print(1)" ||
		len(u.GetResults()) != 1 || u.GetResults()[0].GetMemoryKb() != 9000 ||
		!u.GetUpdateTime().AsTime().After(sub.GetUpdateTime().AsTime()) {
		t.Fatalf("update not applied: %v", u)
	}

	// Unset fields are left alone; a present-but-empty results clears them.
	upd, err = e.dao.UpdateSubmission(ctx(t), &ojv1.UpdateSubmissionRequest{Id: sub.GetId(), Message: proto.String("")})
	if err != nil || upd.GetSubmission().GetVerdict() != ojv1.Verdict_VERDICT_ACCEPTED || len(upd.GetSubmission().GetResults()) != 1 ||
		upd.GetSubmission().GetMessage() != "" {
		t.Fatalf("partial update: %v %v", upd, err)
	}
	upd, err = e.dao.UpdateSubmission(ctx(t), &ojv1.UpdateSubmissionRequest{Id: sub.GetId(), Results: &ojv1.TestResults{}})
	if err != nil || len(upd.GetSubmission().GetResults()) != 0 {
		t.Fatalf("clear results: %v %v", upd, err)
	}

	bad := []*ojv1.UpdateSubmissionRequest{
		{},
		{Id: sub.GetId(), Status: ojv1.SubmissionStatus_SUBMISSION_STATUS_UNSPECIFIED.Enum()},
		{Id: sub.GetId(), Status: ojv1.SubmissionStatus(42).Enum()},
		{Id: sub.GetId(), Verdict: ojv1.Verdict(42).Enum()},
		{Id: sub.GetId(), ExpectedStatuses: []ojv1.SubmissionStatus{ojv1.SubmissionStatus_SUBMISSION_STATUS_UNSPECIFIED}},
		{Id: sub.GetId(), Results: &ojv1.TestResults{Results: []*ojv1.TestResult{{Verdict: 42}}}},
	}
	for i, req := range bad {
		_, err := e.dao.UpdateSubmission(ctx(t), req)
		if status.Code(err) != codes.InvalidArgument {
			t.Errorf("bad update %d: %v", i, err)
		}
	}
	_, err = e.dao.UpdateSubmission(ctx(t), &ojv1.UpdateSubmissionRequest{Id: 999, Passed: proto.Int32(1)})
	wantCode(t, err, codes.NotFound)

	got, err := e.dao.GetSubmission(ctx(t), &ojv1.GetSubmissionRequest{Id: bob.GetId()})
	if err != nil || got.GetSubmission().GetUsername() != "bob" {
		t.Fatalf("get: %v %v", got, err)
	}
	_, err = e.dao.GetSubmission(ctx(t), &ojv1.GetSubmissionRequest{Id: 999})
	wantCode(t, err, codes.NotFound)
	_, err = e.dao.GetSubmission(ctx(t), &ojv1.GetSubmissionRequest{})
	wantCode(t, err, codes.InvalidArgument)
}

func TestUpdateSubmissionCompareAndSet(t *testing.T) {
	e := newEnv(t)
	pid := newProblem(t, e, "cas").GetProblem().GetId()
	sub := newSubmission(t, e, pid, "alice")
	pending, judging := ojv1.SubmissionStatus_SUBMISSION_STATUS_PENDING, ojv1.SubmissionStatus_SUBMISSION_STATUS_JUDGING
	finished := ojv1.SubmissionStatus_SUBMISSION_STATUS_FINISHED

	_, err := e.dao.UpdateSubmission(ctx(t), &ojv1.UpdateSubmissionRequest{
		Id: sub.GetId(), Status: judging.Enum(), ExpectedStatuses: []ojv1.SubmissionStatus{pending}})
	if err != nil {
		t.Fatal(err)
	}
	_, err = e.dao.UpdateSubmission(ctx(t), &ojv1.UpdateSubmissionRequest{
		Id: sub.GetId(), Status: finished.Enum(), Verdict: ojv1.Verdict_VERDICT_ACCEPTED.Enum(),
		ExpectedStatuses: []ojv1.SubmissionStatus{pending, judging}})
	if err != nil {
		t.Fatal(err)
	}
	// Duplicate result after the submission finished.
	_, err = e.dao.UpdateSubmission(ctx(t), &ojv1.UpdateSubmissionRequest{
		Id: sub.GetId(), Verdict: ojv1.Verdict_VERDICT_WRONG_ANSWER.Enum(),
		ExpectedStatuses: []ojv1.SubmissionStatus{pending, judging}})
	wantCode(t, err, codes.FailedPrecondition)
	got, _ := e.dao.GetSubmission(ctx(t), &ojv1.GetSubmissionRequest{Id: sub.GetId()})
	if got.GetSubmission().GetVerdict() != ojv1.Verdict_VERDICT_ACCEPTED {
		t.Fatalf("failed CAS must not write: %v", got)
	}
	_, err = e.dao.UpdateSubmission(ctx(t), &ojv1.UpdateSubmissionRequest{
		Id: 999, Status: judging.Enum(), ExpectedStatuses: []ojv1.SubmissionStatus{pending}})
	wantCode(t, err, codes.NotFound)
}

func TestListSubmissions(t *testing.T) {
	e := newEnv(t)
	p1 := newProblem(t, e, "p1").GetProblem().GetId()
	p2 := newProblem(t, e, "p2").GetProblem().GetId()
	a := newSubmission(t, e, p1, "alice")
	time.Sleep(2 * time.Millisecond)
	b := newSubmission(t, e, p1, "bob")
	time.Sleep(2 * time.Millisecond)
	c := newSubmission(t, e, p2, "alice")
	_, err := e.dao.UpdateSubmission(ctx(t), &ojv1.UpdateSubmissionRequest{
		Id: c.GetId(), Status: ojv1.SubmissionStatus_SUBMISSION_STATUS_JUDGING.Enum()})
	if err != nil {
		t.Fatal(err)
	}

	check := func(name string, req *ojv1.ListSubmissionsRequest, want ...*ojv1.Submission) {
		t.Helper()
		resp, err := e.dao.ListSubmissions(ctx(t), req)
		if err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		got := resp.GetSubmissions()
		if len(got) != len(want) {
			t.Fatalf("%s: got %d submissions, want %d", name, len(got), len(want))
		}
		for i := range got {
			if got[i].GetId() != want[i].GetId() {
				t.Fatalf("%s: position %d is %d, want %d", name, i, got[i].GetId(), want[i].GetId())
			}
			if got[i].GetSource() == "" {
				t.Fatalf("%s: list responses must be complete", name)
			}
		}
	}
	check("all", &ojv1.ListSubmissionsRequest{}, c, b, a)
	check("problem", &ojv1.ListSubmissionsRequest{ProblemId: p1}, b, a)
	check("username", &ojv1.ListSubmissionsRequest{Username: "bob"}, b)
	check("statuses", &ojv1.ListSubmissionsRequest{Statuses: []ojv1.SubmissionStatus{
		ojv1.SubmissionStatus_SUBMISSION_STATUS_JUDGING, ojv1.SubmissionStatus_SUBMISSION_STATUS_FINISHED}}, c)
	check("limit", &ojv1.ListSubmissionsRequest{ProblemId: p1, Limit: 1}, b)
	check("offset", &ojv1.ListSubmissionsRequest{Limit: 1, Offset: 2}, a)
	check("updated_before", &ojv1.ListSubmissionsRequest{UpdatedBefore: b.GetUpdateTime()}, a)
	check("unknown problem", &ojv1.ListSubmissionsRequest{ProblemId: 999})

	bad := []*ojv1.ListSubmissionsRequest{
		{Limit: -1},
		{Limit: 501},
		{Offset: -1},
		{Statuses: []ojv1.SubmissionStatus{ojv1.SubmissionStatus_SUBMISSION_STATUS_UNSPECIFIED}},
		{UpdatedBefore: &timestamppb.Timestamp{Nanos: -1}},
	}
	for i, req := range bad {
		_, err := e.dao.ListSubmissions(ctx(t), req)
		if status.Code(err) != codes.InvalidArgument {
			t.Errorf("bad list %d: %v", i, err)
		}
	}
	if _, err := e.dao.ListSubmissions(ctx(t), &ojv1.ListSubmissionsRequest{Limit: 500}); err != nil {
		t.Fatalf("limit 500 is allowed: %v", err)
	}
}

func TestDeleteProblemCascades(t *testing.T) {
	e := newEnv(t)
	pid := newProblem(t, e, "gone", &ojv1.TestCase{Input: "1"}).GetProblem().GetId()
	sub := newSubmission(t, e, pid, "alice")
	if _, err := e.dao.DeleteProblem(ctx(t), &ojv1.DeleteProblemRequest{Id: pid}); err != nil {
		t.Fatal(err)
	}
	_, err := e.dao.GetSubmission(ctx(t), &ojv1.GetSubmissionRequest{Id: sub.GetId()})
	wantCode(t, err, codes.NotFound)
}

package grpcapi

import (
	"testing"
	"time"

	ojv1 "github.com/online-judge/oj-dao/internal/gen/oj/v1"
	"github.com/online-judge/oj-dao/internal/store"
	"google.golang.org/protobuf/proto"
)

// The stored strings are part of the database schema; changing them breaks
// existing deployments.

func TestLanguageMapping(t *testing.T) {
	want := map[ojv1.Language]string{
		ojv1.Language_LANGUAGE_PYTHON: "python", ojv1.Language_LANGUAGE_C: "c",
		ojv1.Language_LANGUAGE_CPP: "cpp", ojv1.Language_LANGUAGE_JAVASCRIPT: "javascript",
	}
	checkEnum(t, ojv1.Language_name, want, languageFromProto, languageToProto)
}

func TestDifficultyMapping(t *testing.T) {
	want := map[ojv1.Difficulty]string{
		ojv1.Difficulty_DIFFICULTY_EASY: "easy", ojv1.Difficulty_DIFFICULTY_MEDIUM: "medium",
		ojv1.Difficulty_DIFFICULTY_HARD: "hard",
	}
	checkEnum(t, ojv1.Difficulty_name, want, difficultyFromProto, difficultyToProto)
}

func TestStatusMapping(t *testing.T) {
	want := map[ojv1.SubmissionStatus]string{
		ojv1.SubmissionStatus_SUBMISSION_STATUS_PENDING:  "PENDING",
		ojv1.SubmissionStatus_SUBMISSION_STATUS_JUDGING:  "JUDGING",
		ojv1.SubmissionStatus_SUBMISSION_STATUS_FINISHED: "FINISHED",
		ojv1.SubmissionStatus_SUBMISSION_STATUS_FAILED:   "FAILED",
	}
	checkEnum(t, ojv1.SubmissionStatus_name, want, statusFromProto, statusToProto)
}

func TestVerdictMapping(t *testing.T) {
	want := map[ojv1.Verdict]string{
		ojv1.Verdict_VERDICT_UNSPECIFIED:           "",
		ojv1.Verdict_VERDICT_ACCEPTED:              "AC",
		ojv1.Verdict_VERDICT_WRONG_ANSWER:          "WA",
		ojv1.Verdict_VERDICT_TIME_LIMIT_EXCEEDED:   "TLE",
		ojv1.Verdict_VERDICT_MEMORY_LIMIT_EXCEEDED: "MLE",
		ojv1.Verdict_VERDICT_OUTPUT_LIMIT_EXCEEDED: "OLE",
		ojv1.Verdict_VERDICT_RUNTIME_ERROR:         "RE",
		ojv1.Verdict_VERDICT_COMPILATION_ERROR:     "CE",
		ojv1.Verdict_VERDICT_INTERNAL_ERROR:        "IE",
	}
	checkEnum(t, ojv1.Verdict_name, want, verdictFromProto, verdictToProto)
}

// checkEnum verifies that every value declared in the proto enum is either
// mapped to exactly the expected string (and round-trips) or rejected, that
// unknown numbers are rejected, and that unknown stored strings read back as
// UNSPECIFIED.
func checkEnum[E ~int32](t *testing.T, names map[int32]string, want map[E]string,
	from func(E) (string, bool), to func(string) E) {
	t.Helper()
	for n, name := range names {
		v := E(n)
		s, ok := from(v)
		exp, mapped := want[v]
		if ok != mapped || s != exp {
			t.Errorf("%s -> (%q, %v), want (%q, %v)", name, s, ok, exp, mapped)
			continue
		}
		if ok && to(s) != v {
			t.Errorf("%s does not round-trip: %q -> %v", name, s, to(s))
		}
	}
	if _, ok := from(E(999)); ok {
		t.Error("unknown enum number must be rejected")
	}
	if got := to("no-such-value"); got != 0 {
		t.Errorf("unknown stored string -> %v, want UNSPECIFIED", got)
	}
}

func TestSubmissionToProto(t *testing.T) {
	created := time.Date(2026, 1, 2, 3, 4, 5, 6000, time.UTC)
	s := store.Submission{
		ID: 7, ProblemID: 3, Username: "bob", Language: store.LanguageCPP, Source: "src",
		Status: store.StatusFinished, Verdict: store.VerdictTimeLimitExceeded,
		Passed: 1, Total: 2, TimeMs: 1500, Message: "Time Limit Exceeded on test 2",
		Results: []store.TestResult{
			{Test: 1, Verdict: store.VerdictAccepted, TimeMs: 12, MemoryKb: 9000, Sample: true},
			{Test: 2, Verdict: store.VerdictTimeLimitExceeded, TimeMs: 1500, MemoryKb: 1 << 33},
		},
		CreatedAt: created, UpdatedAt: created.Add(time.Second),
	}
	got := submissionToProto(s)
	want := &ojv1.Submission{
		Id: 7, ProblemId: 3, Username: "bob", Language: ojv1.Language_LANGUAGE_CPP, Source: "src",
		Status: ojv1.SubmissionStatus_SUBMISSION_STATUS_FINISHED, Verdict: ojv1.Verdict_VERDICT_TIME_LIMIT_EXCEEDED,
		Passed: 1, Total: 2, TimeMs: 1500, Message: "Time Limit Exceeded on test 2",
		Results: []*ojv1.TestResult{
			{Test: 1, Verdict: ojv1.Verdict_VERDICT_ACCEPTED, TimeMs: 12, MemoryKb: 9000, Sample: true},
			{Test: 2, Verdict: ojv1.Verdict_VERDICT_TIME_LIMIT_EXCEEDED, TimeMs: 1500, MemoryKb: 1 << 33},
		},
		CreateTime: timestampToProto(created), UpdateTime: timestampToProto(created.Add(time.Second)),
	}
	if !proto.Equal(got, want) {
		t.Fatalf("got %v\nwant %v", got, want)
	}
	if !got.GetCreateTime().AsTime().Equal(created) {
		t.Fatalf("timestamp lost precision: %v", got.GetCreateTime().AsTime())
	}
	// Results survive a proto round trip.
	for i, r := range got.GetResults() {
		back, ok := testResultFromProto(r)
		if !ok || back != s.Results[i] {
			t.Fatalf("result %d round trip: %+v", i, back)
		}
	}
}

func TestProblemFromProto(t *testing.T) {
	ok := &ojv1.Problem{Id: 99, Slug: " a-plus-b ", Title: " A + B ", Statement: "md", Difficulty: ojv1.Difficulty_DIFFICULTY_MEDIUM}
	p, err := problemFromProto(ok)
	if err != nil {
		t.Fatal(err)
	}
	if p.ID != 0 || p.Slug != "a-plus-b" || p.Title != "A + B" || p.Difficulty != "medium" ||
		p.TimeLimitMs != DefaultTimeLimitMs || p.MemoryLimitMb != DefaultMemoryLimitMb {
		t.Fatalf("unexpected: %+v", p)
	}
	back := problemToProto(p)
	if back.GetDifficulty() != ojv1.Difficulty_DIFFICULTY_MEDIUM || back.GetCreateTime() != nil {
		t.Fatalf("to proto: %v", back)
	}

	long := make([]byte, 65)
	for i := range long {
		long[i] = 'a'
	}
	bad := []*ojv1.Problem{
		nil,
		{Slug: "", Title: "t", Difficulty: ojv1.Difficulty_DIFFICULTY_EASY},
		{Slug: "Upper", Title: "t", Difficulty: ojv1.Difficulty_DIFFICULTY_EASY},
		{Slug: "a--b", Title: "t", Difficulty: ojv1.Difficulty_DIFFICULTY_EASY},
		{Slug: string(long), Title: "t", Difficulty: ojv1.Difficulty_DIFFICULTY_EASY},
		{Slug: "ok", Title: " ", Difficulty: ojv1.Difficulty_DIFFICULTY_EASY},
		{Slug: "ok", Title: "t"},
		{Slug: "ok", Title: "t", Difficulty: 42},
		{Slug: "ok", Title: "t", Difficulty: ojv1.Difficulty_DIFFICULTY_EASY, TimeLimitMs: -1},
	}
	for i, b := range bad {
		if _, err := problemFromProto(b); err == nil {
			t.Errorf("case %d: expected an error for %v", i, b)
		}
	}
}

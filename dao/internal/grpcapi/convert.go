package grpcapi

import (
	"log/slog"
	"time"

	ojv1 "github.com/online-judge/online-judge/dao/internal/gen/oj/v1"
	"github.com/online-judge/online-judge/dao/internal/store"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// This file is the single place where protobuf enums map to the strings
// stored in the database. Every mapping is a bijection over the known
// values; *FromProto returns ok=false for values that cannot be stored.

var languages = map[ojv1.Language]string{
	ojv1.Language_LANGUAGE_PYTHON:     store.LanguagePython,
	ojv1.Language_LANGUAGE_C:          store.LanguageC,
	ojv1.Language_LANGUAGE_CPP:        store.LanguageCPP,
	ojv1.Language_LANGUAGE_JAVASCRIPT: store.LanguageJavaScript,
}

var difficulties = map[ojv1.Difficulty]string{
	ojv1.Difficulty_DIFFICULTY_EASY:   store.DifficultyEasy,
	ojv1.Difficulty_DIFFICULTY_MEDIUM: store.DifficultyMedium,
	ojv1.Difficulty_DIFFICULTY_HARD:   store.DifficultyHard,
}

var statuses = map[ojv1.SubmissionStatus]string{
	ojv1.SubmissionStatus_SUBMISSION_STATUS_PENDING:  store.StatusPending,
	ojv1.SubmissionStatus_SUBMISSION_STATUS_JUDGING:  store.StatusJudging,
	ojv1.SubmissionStatus_SUBMISSION_STATUS_FINISHED: store.StatusFinished,
	ojv1.SubmissionStatus_SUBMISSION_STATUS_FAILED:   store.StatusFailed,
}

// VERDICT_UNSPECIFIED is a storable value: it means "not judged yet".
var verdicts = map[ojv1.Verdict]string{
	ojv1.Verdict_VERDICT_UNSPECIFIED:           store.VerdictNone,
	ojv1.Verdict_VERDICT_ACCEPTED:              store.VerdictAccepted,
	ojv1.Verdict_VERDICT_WRONG_ANSWER:          store.VerdictWrongAnswer,
	ojv1.Verdict_VERDICT_TIME_LIMIT_EXCEEDED:   store.VerdictTimeLimitExceeded,
	ojv1.Verdict_VERDICT_MEMORY_LIMIT_EXCEEDED: store.VerdictMemoryLimitExceeded,
	ojv1.Verdict_VERDICT_OUTPUT_LIMIT_EXCEEDED: store.VerdictOutputLimitExceeded,
	ojv1.Verdict_VERDICT_RUNTIME_ERROR:         store.VerdictRuntimeError,
	ojv1.Verdict_VERDICT_COMPILATION_ERROR:     store.VerdictCompilationError,
	ojv1.Verdict_VERDICT_INTERNAL_ERROR:        store.VerdictInternalError,
}

func invert[K comparable, V comparable](m map[K]V) map[V]K {
	out := make(map[V]K, len(m))
	for k, v := range m {
		out[v] = k
	}
	return out
}

var (
	languagesByDB    = invert(languages)
	difficultiesByDB = invert(difficulties)
	statusesByDB     = invert(statuses)
	verdictsByDB     = invert(verdicts)
)

func languageFromProto(v ojv1.Language) (string, bool) { s, ok := languages[v]; return s, ok }
func difficultyFromProto(v ojv1.Difficulty) (string, bool) {
	s, ok := difficulties[v]
	return s, ok
}
func statusFromProto(v ojv1.SubmissionStatus) (string, bool) { s, ok := statuses[v]; return s, ok }
func verdictFromProto(v ojv1.Verdict) (string, bool)         { s, ok := verdicts[v]; return s, ok }

// The *ToProto functions map unknown stored strings (legacy or manually
// edited rows) to UNSPECIFIED and log them, rather than failing reads.

func languageToProto(s string) ojv1.Language {
	return lookup(languagesByDB, s, "language")
}
func difficultyToProto(s string) ojv1.Difficulty {
	return lookup(difficultiesByDB, s, "difficulty")
}
func statusToProto(s string) ojv1.SubmissionStatus {
	return lookup(statusesByDB, s, "status")
}
func verdictToProto(s string) ojv1.Verdict {
	return lookup(verdictsByDB, s, "verdict")
}

func lookup[E ~int32](m map[string]E, s, what string) E {
	v, ok := m[s]
	if !ok {
		slog.Warn("unknown stored enum value", "field", what, "value", s)
	}
	return v
}

// ---------- models ----------

func timestampToProto(t time.Time) *timestamppb.Timestamp {
	if t.IsZero() {
		return nil
	}
	return timestamppb.New(t)
}

func problemToProto(p store.Problem) *ojv1.Problem {
	return &ojv1.Problem{
		Id:            p.ID,
		Slug:          p.Slug,
		Title:         p.Title,
		Statement:     p.Statement,
		Difficulty:    difficultyToProto(p.Difficulty),
		TimeLimitMs:   int32(p.TimeLimitMs),
		MemoryLimitMb: int32(p.MemoryLimitMb),
		CreateTime:    timestampToProto(p.CreatedAt),
	}
}

func testCaseToProto(tc store.TestCase) *ojv1.TestCase {
	return &ojv1.TestCase{
		Id:             tc.ID,
		ProblemId:      tc.ProblemID,
		Input:          tc.Input,
		ExpectedOutput: tc.ExpectedOutput,
		IsSample:       tc.IsSample,
		Ordinal:        int32(tc.Ordinal),
	}
}

func testCasesToProto(tcs []store.TestCase) []*ojv1.TestCase {
	out := make([]*ojv1.TestCase, len(tcs))
	for i, tc := range tcs {
		out[i] = testCaseToProto(tc)
	}
	return out
}

func testResultToProto(r store.TestResult) *ojv1.TestResult {
	return &ojv1.TestResult{
		Test:     int32(r.Test),
		Verdict:  verdictToProto(r.Verdict),
		TimeMs:   int32(r.TimeMs),
		MemoryKb: r.MemoryKb,
		Sample:   r.Sample,
	}
}

func testResultFromProto(r *ojv1.TestResult) (store.TestResult, bool) {
	v, ok := verdictFromProto(r.GetVerdict())
	if !ok {
		return store.TestResult{}, false
	}
	return store.TestResult{
		Test:     int(r.GetTest()),
		Verdict:  v,
		TimeMs:   int(r.GetTimeMs()),
		MemoryKb: r.GetMemoryKb(),
		Sample:   r.GetSample(),
	}, true
}

func submissionToProto(s store.Submission) *ojv1.Submission {
	results := make([]*ojv1.TestResult, len(s.Results))
	for i, r := range s.Results {
		results[i] = testResultToProto(r)
	}
	return &ojv1.Submission{
		Id:         s.ID,
		ProblemId:  s.ProblemID,
		Username:   s.Username,
		Language:   languageToProto(s.Language),
		Source:     s.Source,
		Status:     statusToProto(s.Status),
		Verdict:    verdictToProto(s.Verdict),
		Passed:     int32(s.Passed),
		Total:      int32(s.Total),
		TimeMs:     int32(s.TimeMs),
		Message:    s.Message,
		Results:    results,
		CreateTime: timestampToProto(s.CreatedAt),
		UpdateTime: timestampToProto(s.UpdatedAt),
	}
}

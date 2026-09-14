// Package store defines the domain models and the persistence contract
// for the online judge, together with its implementations. It is the only
// package that talks to the database.
//
// Enum-like fields hold the strings stored in the database (see the
// constants below); translating them to and from protobuf is the job of the
// gRPC layer.
package store

import (
	"context"
	"errors"
	"time"
)

var (
	// ErrNotFound is returned when the requested entity (or a referenced
	// parent entity) does not exist.
	ErrNotFound = errors.New("not found")
	// ErrConflict is returned when a uniqueness constraint is violated.
	ErrConflict = errors.New("conflict")
	// ErrPrecondition is returned by UpdateSubmission when the submission's
	// current status is not one of SubmissionUpdate.ExpectedStatuses.
	ErrPrecondition = errors.New("precondition failed")
	// ErrUnavailable wraps errors caused by the database being unreachable.
	ErrUnavailable = errors.New("database unavailable")
)

// Submission lifecycle states (submissions.status).
const (
	StatusPending  = "PENDING"
	StatusJudging  = "JUDGING"
	StatusFinished = "FINISHED"
	StatusFailed   = "FAILED"
)

// Verdicts (submissions.verdict and results[].verdict). VerdictNone means
// "not judged yet".
const (
	VerdictNone                = ""
	VerdictAccepted            = "AC"
	VerdictWrongAnswer         = "WA"
	VerdictTimeLimitExceeded   = "TLE"
	VerdictMemoryLimitExceeded = "MLE"
	VerdictOutputLimitExceeded = "OLE"
	VerdictRuntimeError        = "RE"
	VerdictCompilationError    = "CE"
	VerdictInternalError       = "IE"
)

// Languages (submissions.language).
const (
	LanguagePython     = "python"
	LanguageC          = "c"
	LanguageCPP        = "cpp"
	LanguageJavaScript = "javascript"
)

// Difficulties (problems.difficulty).
const (
	DifficultyEasy   = "easy"
	DifficultyMedium = "medium"
	DifficultyHard   = "hard"
)

// DefaultListLimit is used by ListSubmissions when SubmissionFilter.Limit is 0.
const DefaultListLimit = 50

type Problem struct {
	ID            int64
	Slug          string
	Title         string
	Statement     string
	Difficulty    string
	TimeLimitMs   int
	MemoryLimitMb int
	CreatedAt     time.Time
}

type TestCase struct {
	ID             int64
	ProblemID      int64
	Input          string
	ExpectedOutput string
	IsSample       bool
	Ordinal        int
}

// TestResult is one element of submissions.results. The JSON tags are the
// stored row format and must not change.
type TestResult struct {
	Test     int    `json:"test"`
	Verdict  string `json:"verdict"`
	TimeMs   int    `json:"time_ms"`
	MemoryKb int64  `json:"memory_kb"`
	Sample   bool   `json:"sample"`
}

type Submission struct {
	ID        int64
	ProblemID int64
	Username  string
	Language  string
	Source    string
	Status    string
	Verdict   string
	Passed    int
	Total     int
	TimeMs    int
	Message   string
	Results   []TestResult
	CreatedAt time.Time
	UpdatedAt time.Time
}

// SubmissionUpdate is a partial update; nil fields are left unchanged.
// UpdatedAt is always bumped.
type SubmissionUpdate struct {
	Status  *string
	Verdict *string
	Passed  *int
	Total   *int
	TimeMs  *int
	Message *string
	// Results replaces the stored results when non-nil (an empty slice
	// clears them).
	Results *[]TestResult
	// ExpectedStatuses, when non-empty, makes the update a compare-and-set:
	// it is applied only if the current status is one of these, otherwise
	// ErrPrecondition is returned and nothing changes.
	ExpectedStatuses []string
}

// SubmissionFilter selects submissions; zero values mean "any".
type SubmissionFilter struct {
	ProblemID int64
	Username  string
	// Statuses matches any of the given statuses.
	Statuses []string
	// UpdatedBefore keeps submissions with UpdatedAt strictly before it.
	UpdatedBefore time.Time
	// Limit is the page size; 0 means DefaultListLimit.
	Limit  int
	Offset int
}

// Store is the persistence contract used by the gRPC layer.
type Store interface {
	Ping(ctx context.Context) error

	ListProblems(ctx context.Context) ([]Problem, error)
	GetProblem(ctx context.Context, id int64) (Problem, error)
	// CreateProblem inserts the problem and its test cases atomically. The
	// test cases' ProblemID and Ordinal are assigned (1..n in slice order).
	CreateProblem(ctx context.Context, p Problem, tcs []TestCase) (Problem, []TestCase, error)
	UpdateProblem(ctx context.Context, p Problem) (Problem, error)
	// DeleteProblem cascades to test cases and submissions.
	DeleteProblem(ctx context.Context, id int64) error

	// ListTestCases returns the problem's test cases ordered by ordinal, or
	// ErrNotFound if the problem does not exist.
	ListTestCases(ctx context.Context, problemID int64, samplesOnly bool) ([]TestCase, error)
	// CreateTestCase appends a test case; its Ordinal is max(ordinal)+1.
	CreateTestCase(ctx context.Context, tc TestCase) (TestCase, error)
	DeleteTestCase(ctx context.Context, problemID, id int64) error

	// CreateSubmission stores a new PENDING submission.
	CreateSubmission(ctx context.Context, s Submission) (Submission, error)
	GetSubmission(ctx context.Context, id int64) (Submission, error)
	// ListSubmissions returns matching submissions, newest first.
	ListSubmissions(ctx context.Context, f SubmissionFilter) ([]Submission, error)
	UpdateSubmission(ctx context.Context, id int64, u SubmissionUpdate) (Submission, error)
}

// now returns the current time at the database's (microsecond) precision.
func now() time.Time { return time.Now().UTC().Truncate(time.Microsecond) }

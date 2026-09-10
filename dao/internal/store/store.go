// Package store defines the domain models and the persistence contract
// for the online judge, together with its implementations.
package store

import (
	"context"
	"encoding/json"
	"errors"
	"time"
)

var (
	// ErrNotFound is returned when the requested entity (or a referenced
	// parent entity) does not exist.
	ErrNotFound = errors.New("not found")
	// ErrConflict is returned when a uniqueness constraint is violated.
	ErrConflict = errors.New("conflict")
)

// Submission lifecycle states.
const (
	StatusPending  = "PENDING"
	StatusJudging  = "JUDGING"
	StatusFinished = "FINISHED"
	StatusFailed   = "FAILED"
)

type Problem struct {
	ID            int64     `json:"id"`
	Slug          string    `json:"slug"`
	Title         string    `json:"title"`
	Statement     string    `json:"statement"`
	Difficulty    string    `json:"difficulty"`
	TimeLimitMs   int       `json:"time_limit_ms"`
	MemoryLimitMb int       `json:"memory_limit_mb"`
	CreatedAt     time.Time `json:"created_at"`
}

type TestCase struct {
	ID             int64  `json:"id"`
	ProblemID      int64  `json:"problem_id"`
	Input          string `json:"input"`
	ExpectedOutput string `json:"expected_output"`
	IsSample       bool   `json:"is_sample"`
	Ordinal        int    `json:"ordinal"`
}

type Submission struct {
	ID        int64           `json:"id"`
	ProblemID int64           `json:"problem_id"`
	Username  string          `json:"username"`
	Language  string          `json:"language"`
	Source    string          `json:"source"`
	Status    string          `json:"status"`
	Verdict   string          `json:"verdict"`
	Passed    int             `json:"passed"`
	Total     int             `json:"total"`
	TimeMs    int             `json:"time_ms"`
	Message   string          `json:"message"`
	Results   json.RawMessage `json:"results"`
	CreatedAt time.Time       `json:"created_at"`
	UpdatedAt time.Time       `json:"updated_at"`
}

// SubmissionUpdate is a partial update; nil fields are left unchanged.
type SubmissionUpdate struct {
	Status  *string          `json:"status,omitempty"`
	Verdict *string          `json:"verdict,omitempty"`
	Passed  *int             `json:"passed,omitempty"`
	Total   *int             `json:"total,omitempty"`
	TimeMs  *int             `json:"time_ms,omitempty"`
	Message *string          `json:"message,omitempty"`
	Results *json.RawMessage `json:"results,omitempty"`
}

type SubmissionFilter struct {
	ProblemID int64
	Username  string
	Status    string
	Limit     int
	Offset    int
}

// Store is the persistence contract used by the HTTP layer.
type Store interface {
	Ping(ctx context.Context) error

	ListProblems(ctx context.Context) ([]Problem, error)
	GetProblem(ctx context.Context, id int64) (Problem, error)
	CreateProblem(ctx context.Context, p Problem) (Problem, error)
	UpdateProblem(ctx context.Context, p Problem) (Problem, error)
	DeleteProblem(ctx context.Context, id int64) error

	ListTestCases(ctx context.Context, problemID int64, samplesOnly bool) ([]TestCase, error)
	CreateTestCase(ctx context.Context, tc TestCase) (TestCase, error)
	DeleteTestCase(ctx context.Context, problemID, id int64) error

	CreateSubmission(ctx context.Context, s Submission) (Submission, error)
	GetSubmission(ctx context.Context, id int64) (Submission, error)
	ListSubmissions(ctx context.Context, f SubmissionFilter) ([]Submission, error)
	UpdateSubmission(ctx context.Context, id int64, u SubmissionUpdate) (Submission, error)
}

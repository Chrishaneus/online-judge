package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Postgres is the production Store backed by PostgreSQL.
type Postgres struct {
	pool *pgxpool.Pool
}

// NewPostgres connects to the database, retrying until ctx is done. Retrying
// makes container start-up order irrelevant.
func NewPostgres(ctx context.Context, dsn string) (*Postgres, error) {
	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, fmt.Errorf("parse dsn: %w", err)
	}
	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, err
	}
	for {
		pingCtx, cancel := context.WithTimeout(ctx, 2*time.Second)
		err = pool.Ping(pingCtx)
		cancel()
		if err == nil {
			return &Postgres{pool: pool}, nil
		}
		select {
		case <-ctx.Done():
			pool.Close()
			return nil, fmt.Errorf("connect to postgres: %w", err)
		case <-time.After(time.Second):
		}
	}
}

func (p *Postgres) Close() { p.pool.Close() }

func (p *Postgres) Ping(ctx context.Context) error { return p.pool.Ping(ctx) }

// mapErr translates driver errors into store sentinel errors.
func mapErr(err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrNotFound
	}
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) {
		switch pgErr.Code {
		case "23505": // unique_violation
			return ErrConflict
		case "23503": // foreign_key_violation
			return ErrNotFound
		}
	}
	return err
}

// ---------- problems ----------

const problemCols = "id, slug, title, statement, difficulty, time_limit_ms, memory_limit_mb, created_at"

func scanProblem(row pgx.Row) (Problem, error) {
	var p Problem
	err := row.Scan(&p.ID, &p.Slug, &p.Title, &p.Statement, &p.Difficulty,
		&p.TimeLimitMs, &p.MemoryLimitMb, &p.CreatedAt)
	return p, mapErr(err)
}

func (p *Postgres) ListProblems(ctx context.Context) ([]Problem, error) {
	rows, err := p.pool.Query(ctx, "SELECT "+problemCols+" FROM problems ORDER BY id")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Problem{}
	for rows.Next() {
		pr, err := scanProblem(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, pr)
	}
	return out, rows.Err()
}

func (p *Postgres) GetProblem(ctx context.Context, id int64) (Problem, error) {
	return scanProblem(p.pool.QueryRow(ctx, "SELECT "+problemCols+" FROM problems WHERE id = $1", id))
}

func (p *Postgres) CreateProblem(ctx context.Context, pr Problem) (Problem, error) {
	return scanProblem(p.pool.QueryRow(ctx, `
		INSERT INTO problems (slug, title, statement, difficulty, time_limit_ms, memory_limit_mb)
		VALUES ($1, $2, $3, $4, $5, $6)
		RETURNING `+problemCols,
		pr.Slug, pr.Title, pr.Statement, pr.Difficulty, pr.TimeLimitMs, pr.MemoryLimitMb))
}

func (p *Postgres) UpdateProblem(ctx context.Context, pr Problem) (Problem, error) {
	return scanProblem(p.pool.QueryRow(ctx, `
		UPDATE problems
		SET slug = $2, title = $3, statement = $4, difficulty = $5,
		    time_limit_ms = $6, memory_limit_mb = $7
		WHERE id = $1
		RETURNING `+problemCols,
		pr.ID, pr.Slug, pr.Title, pr.Statement, pr.Difficulty, pr.TimeLimitMs, pr.MemoryLimitMb))
}

func (p *Postgres) DeleteProblem(ctx context.Context, id int64) error {
	tag, err := p.pool.Exec(ctx, "DELETE FROM problems WHERE id = $1", id)
	if err != nil {
		return mapErr(err)
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// ---------- test cases ----------

const testCaseCols = "id, problem_id, input, expected_output, is_sample, ordinal"

func scanTestCase(row pgx.Row) (TestCase, error) {
	var tc TestCase
	err := row.Scan(&tc.ID, &tc.ProblemID, &tc.Input, &tc.ExpectedOutput, &tc.IsSample, &tc.Ordinal)
	return tc, mapErr(err)
}

func (p *Postgres) ListTestCases(ctx context.Context, problemID int64, samplesOnly bool) ([]TestCase, error) {
	if _, err := p.GetProblem(ctx, problemID); err != nil {
		return nil, err
	}
	rows, err := p.pool.Query(ctx, `
		SELECT `+testCaseCols+` FROM test_cases
		WHERE problem_id = $1 AND (NOT $2 OR is_sample)
		ORDER BY ordinal, id`, problemID, samplesOnly)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []TestCase{}
	for rows.Next() {
		tc, err := scanTestCase(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, tc)
	}
	return out, rows.Err()
}

func (p *Postgres) CreateTestCase(ctx context.Context, tc TestCase) (TestCase, error) {
	return scanTestCase(p.pool.QueryRow(ctx, `
		INSERT INTO test_cases (problem_id, input, expected_output, is_sample, ordinal)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING `+testCaseCols,
		tc.ProblemID, tc.Input, tc.ExpectedOutput, tc.IsSample, tc.Ordinal))
}

func (p *Postgres) DeleteTestCase(ctx context.Context, problemID, id int64) error {
	tag, err := p.pool.Exec(ctx, "DELETE FROM test_cases WHERE id = $1 AND problem_id = $2", id, problemID)
	if err != nil {
		return mapErr(err)
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// ---------- submissions ----------

const submissionCols = `id, problem_id, username, language, source, status, verdict,
	passed, total, time_ms, message, results, created_at, updated_at`

func scanSubmission(row pgx.Row) (Submission, error) {
	var s Submission
	var results []byte
	err := row.Scan(&s.ID, &s.ProblemID, &s.Username, &s.Language, &s.Source, &s.Status,
		&s.Verdict, &s.Passed, &s.Total, &s.TimeMs, &s.Message, &results, &s.CreatedAt, &s.UpdatedAt)
	s.Results = json.RawMessage(results)
	return s, mapErr(err)
}

func (p *Postgres) CreateSubmission(ctx context.Context, s Submission) (Submission, error) {
	if s.Status == "" {
		s.Status = StatusPending
	}
	if len(s.Results) == 0 {
		s.Results = json.RawMessage("[]")
	}
	return scanSubmission(p.pool.QueryRow(ctx, `
		INSERT INTO submissions (problem_id, username, language, source, status, results)
		VALUES ($1, $2, $3, $4, $5, $6::jsonb)
		RETURNING `+submissionCols,
		s.ProblemID, s.Username, s.Language, s.Source, s.Status, string(s.Results)))
}

func (p *Postgres) GetSubmission(ctx context.Context, id int64) (Submission, error) {
	return scanSubmission(p.pool.QueryRow(ctx, "SELECT "+submissionCols+" FROM submissions WHERE id = $1", id))
}

func (p *Postgres) ListSubmissions(ctx context.Context, f SubmissionFilter) ([]Submission, error) {
	var (
		where []string
		args  []any
	)
	if f.ProblemID != 0 {
		args = append(args, f.ProblemID)
		where = append(where, fmt.Sprintf("problem_id = $%d", len(args)))
	}
	if f.Username != "" {
		args = append(args, f.Username)
		where = append(where, fmt.Sprintf("username = $%d", len(args)))
	}
	q := "SELECT " + submissionCols + " FROM submissions"
	if len(where) > 0 {
		q += " WHERE " + strings.Join(where, " AND ")
	}
	limit := f.Limit
	if limit <= 0 {
		limit = 50
	}
	args = append(args, limit, f.Offset)
	q += fmt.Sprintf(" ORDER BY id DESC LIMIT $%d OFFSET $%d", len(args)-1, len(args))

	rows, err := p.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Submission{}
	for rows.Next() {
		s, err := scanSubmission(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	return out, rows.Err()
}

func (p *Postgres) UpdateSubmission(ctx context.Context, id int64, u SubmissionUpdate) (Submission, error) {
	var results *string
	if u.Results != nil {
		r := string(*u.Results)
		results = &r
	}
	return scanSubmission(p.pool.QueryRow(ctx, `
		UPDATE submissions SET
			status     = COALESCE($2::text, status),
			verdict    = COALESCE($3::text, verdict),
			passed     = COALESCE($4::int,  passed),
			total      = COALESCE($5::int,  total),
			time_ms    = COALESCE($6::int,  time_ms),
			message    = COALESCE($7::text, message),
			results    = COALESCE($8::jsonb, results),
			updated_at = now()
		WHERE id = $1
		RETURNING `+submissionCols,
		id, u.Status, u.Verdict, u.Passed, u.Total, u.TimeMs, u.Message, results))
}

package store

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
)

// PostgreSQL-only behaviour. Skipped unless TEST_DATABASE_URL is set.

func TestPostgresCreateProblemIsAtomic(t *testing.T) {
	pg := newTestPostgres(t)
	ctx := context.Background()
	// PostgreSQL rejects NUL bytes in TEXT, so the second insert fails.
	_, _, err := pg.CreateProblem(ctx, Problem{Slug: "atomic", Title: "A", Difficulty: DifficultyEasy},
		[]TestCase{{Input: "ok"}, {Input: "bad\x00"}})
	if err == nil {
		t.Fatal("expected an error")
	}
	if _, err := pg.GetProblem(ctx, 1); !errors.Is(err, ErrNotFound) {
		t.Fatalf("problem must be rolled back, got %v", err)
	}
	var n int
	if err := pg.pool.QueryRow(ctx, "SELECT count(*) FROM test_cases").Scan(&n); err != nil || n != 0 {
		t.Fatalf("test cases must be rolled back: %d, %v", n, err)
	}
}

func TestPostgresResultsRowFormat(t *testing.T) {
	pg := newTestPostgres(t)
	ctx := context.Background()
	p, _ := mustProblem(t, pg, "fmt")
	sub := mustSubmission(t, pg, p.ID, "u")
	rs := []TestResult{{Test: 1, Verdict: VerdictAccepted, TimeMs: 12, MemoryKb: 9000, Sample: true}}
	if _, err := pg.UpdateSubmission(ctx, sub.ID, SubmissionUpdate{Results: &rs}); err != nil {
		t.Fatal(err)
	}
	var raw []byte
	if err := pg.pool.QueryRow(ctx, "SELECT results FROM submissions WHERE id = $1", sub.ID).Scan(&raw); err != nil {
		t.Fatal(err)
	}
	var got, want any
	_ = json.Unmarshal(raw, &got)
	_ = json.Unmarshal([]byte(`[{"test":1,"verdict":"AC","time_ms":12,"memory_kb":9000,"sample":true}]`), &want)
	if gb, _ := json.Marshal(got); string(gb) != mustJSON(want) {
		t.Fatalf("stored results = %s", raw)
	}

	// Rows from older versions that don't match the format are read as empty.
	if _, err := pg.pool.Exec(ctx, `UPDATE submissions SET results = '{"weird":true}' WHERE id = $1`, sub.ID); err != nil {
		t.Fatal(err)
	}
	got2, err := pg.GetSubmission(ctx, sub.ID)
	if err != nil || len(got2.Results) != 0 {
		t.Fatalf("malformed results: %+v, %v", got2, err)
	}
}

func mustJSON(v any) string {
	b, _ := json.Marshal(v)
	return string(b)
}

func TestMapErrUnavailable(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := mapErr(ctx.Err()); !errors.Is(err, context.Canceled) {
		t.Fatalf("context errors pass through, got %v", err)
	}
	if err := mapErr(errors.New("boom")); errors.Is(err, ErrUnavailable) {
		t.Fatal("plain errors are not unavailable")
	}
	// Nothing listens on port 1: the pool connects lazily, so Ping fails.
	pool, err := pgxpool.New(context.Background(), "postgres://u:p@127.0.0.1:1/db?connect_timeout=2")
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()
	pg := &Postgres{pool: pool}
	if err := pg.Ping(context.Background()); !errors.Is(err, ErrUnavailable) {
		t.Fatalf("want ErrUnavailable, got %v", err)
	}
	if _, err := pg.GetProblem(context.Background(), 1); !errors.Is(err, ErrUnavailable) {
		t.Fatalf("want ErrUnavailable, got %v", err)
	}
}

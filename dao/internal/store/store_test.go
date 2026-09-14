package store

import (
	"context"
	"errors"
	"os"
	"sort"
	"sync"
	"testing"
	"time"
)

// Every test in this file runs against each Store implementation: the
// in-memory store always, PostgreSQL when TEST_DATABASE_URL points at a
// throwaway database (its tables are truncated!).

type storeFactory struct {
	name string
	new  func(t *testing.T) Store
}

func factories(t *testing.T) []storeFactory {
	t.Helper()
	fs := []storeFactory{{"memory", func(*testing.T) Store { return NewMemory() }}}
	if os.Getenv("TEST_DATABASE_URL") != "" {
		fs = append(fs, storeFactory{"postgres", func(t *testing.T) Store { return newTestPostgres(t) }})
	}
	return fs
}

func newTestPostgres(t *testing.T) *Postgres {
	t.Helper()
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	pg, err := NewPostgres(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pg.Close)
	if err := pg.Migrate(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := pg.pool.Exec(ctx,
		"TRUNCATE problems, test_cases, submissions RESTART IDENTITY CASCADE"); err != nil {
		t.Fatal(err)
	}
	return pg
}

func forEachStore(t *testing.T, fn func(t *testing.T, s Store)) {
	for _, f := range factories(t) {
		t.Run(f.name, func(t *testing.T) { fn(t, f.new(t)) })
	}
}

func mustProblem(t *testing.T, s Store, slug string, tcs ...TestCase) (Problem, []TestCase) {
	t.Helper()
	p, out, err := s.CreateProblem(context.Background(), Problem{
		Slug: slug, Title: "T", Statement: "S", Difficulty: DifficultyEasy, TimeLimitMs: 1000, MemoryLimitMb: 64,
	}, tcs)
	if err != nil {
		t.Fatal(err)
	}
	return p, out
}

func mustSubmission(t *testing.T, s Store, problemID int64, user string) Submission {
	t.Helper()
	sub, err := s.CreateSubmission(context.Background(), Submission{
		ProblemID: problemID, Username: user, Language: LanguagePython, Source: "print(1)",
	})
	if err != nil {
		t.Fatal(err)
	}
	return sub
}

func ptr[T any](v T) *T { return &v }

func TestCreateProblemWithTestCases(t *testing.T) {
	forEachStore(t, func(t *testing.T, s Store) {
		ctx := context.Background()
		p, tcs := mustProblem(t, s, "sum",
			TestCase{Input: "1 2", ExpectedOutput: "3", IsSample: true, Ordinal: 7, ProblemID: 99},
			TestCase{Input: "2 2", ExpectedOutput: "4"},
			TestCase{Input: "", ExpectedOutput: ""},
		)
		if p.ID == 0 || p.CreatedAt.IsZero() {
			t.Fatalf("problem not populated: %+v", p)
		}
		if len(tcs) != 3 {
			t.Fatalf("want 3 test cases, got %d", len(tcs))
		}
		for i, tc := range tcs {
			if tc.Ordinal != i+1 || tc.ProblemID != p.ID || tc.ID == 0 {
				t.Fatalf("test case %d: %+v", i, tc)
			}
		}
		listed, err := s.ListTestCases(ctx, p.ID, false)
		if err != nil || len(listed) != 3 || listed[0].Input != "1 2" || !listed[0].IsSample {
			t.Fatalf("list: %+v, %v", listed, err)
		}
		samples, err := s.ListTestCases(ctx, p.ID, true)
		if err != nil || len(samples) != 1 {
			t.Fatalf("samples: %+v, %v", samples, err)
		}

		if _, _, err := s.CreateProblem(ctx, Problem{Slug: "sum", Title: "x", Difficulty: DifficultyEasy},
			[]TestCase{{Input: "x"}}); !errors.Is(err, ErrConflict) {
			t.Fatalf("duplicate slug: want ErrConflict, got %v", err)
		}
		listed, _ = s.ListTestCases(ctx, p.ID, false)
		if len(listed) != 3 {
			t.Fatalf("failed create must not add test cases, got %d", len(listed))
		}
	})
}

func TestProblemUpdateDeleteCascade(t *testing.T) {
	forEachStore(t, func(t *testing.T, s Store) {
		ctx := context.Background()
		p, _ := mustProblem(t, s, "a", TestCase{Input: "1"})
		mustProblem(t, s, "b")
		sub := mustSubmission(t, s, p.ID, "alice")

		p.Title, p.Difficulty, p.TimeLimitMs = "New", DifficultyHard, 500
		upd, err := s.UpdateProblem(ctx, p)
		if err != nil || upd.Title != "New" || upd.Difficulty != DifficultyHard || upd.TimeLimitMs != 500 ||
			!upd.CreatedAt.Equal(p.CreatedAt) {
			t.Fatalf("update: %+v, %v", upd, err)
		}
		p.Slug = "b"
		if _, err := s.UpdateProblem(ctx, p); !errors.Is(err, ErrConflict) {
			t.Fatalf("want ErrConflict, got %v", err)
		}
		if _, err := s.UpdateProblem(ctx, Problem{ID: 999, Slug: "zz", Difficulty: DifficultyEasy}); !errors.Is(err, ErrNotFound) {
			t.Fatalf("want ErrNotFound, got %v", err)
		}

		if err := s.DeleteProblem(ctx, p.ID); err != nil {
			t.Fatal(err)
		}
		if err := s.DeleteProblem(ctx, p.ID); !errors.Is(err, ErrNotFound) {
			t.Fatalf("want ErrNotFound, got %v", err)
		}
		if _, err := s.GetSubmission(ctx, sub.ID); !errors.Is(err, ErrNotFound) {
			t.Fatalf("submission should cascade, got %v", err)
		}
		if _, err := s.ListTestCases(ctx, p.ID, false); !errors.Is(err, ErrNotFound) {
			t.Fatalf("want ErrNotFound, got %v", err)
		}
		ps, _ := s.ListProblems(ctx)
		if len(ps) != 1 || ps[0].Slug != "b" {
			t.Fatalf("list: %+v", ps)
		}
	})
}

func TestCreateTestCaseOrdinals(t *testing.T) {
	forEachStore(t, func(t *testing.T, s Store) {
		ctx := context.Background()
		p, _ := mustProblem(t, s, "tc", TestCase{Input: "1"}, TestCase{Input: "2"})

		tc, err := s.CreateTestCase(ctx, TestCase{ProblemID: p.ID, Input: "3", Ordinal: 42})
		if err != nil || tc.Ordinal != 3 || tc.ProblemID != p.ID {
			t.Fatalf("append: %+v, %v", tc, err)
		}
		if err := s.DeleteTestCase(ctx, p.ID, tc.ID); err != nil {
			t.Fatal(err)
		}
		if err := s.DeleteTestCase(ctx, p.ID, tc.ID); !errors.Is(err, ErrNotFound) {
			t.Fatalf("want ErrNotFound, got %v", err)
		}
		tc, _ = s.CreateTestCase(ctx, TestCase{ProblemID: p.ID, Input: "3"})
		if tc.Ordinal != 3 {
			t.Fatalf("want ordinal max+1 = 3, got %d", tc.Ordinal)
		}
		if _, err := s.CreateTestCase(ctx, TestCase{ProblemID: 999}); !errors.Is(err, ErrNotFound) {
			t.Fatalf("want ErrNotFound, got %v", err)
		}
		other, _ := mustProblem(t, s, "other")
		if err := s.DeleteTestCase(ctx, other.ID, tc.ID); !errors.Is(err, ErrNotFound) {
			t.Fatalf("wrong problem: want ErrNotFound, got %v", err)
		}
	})
}

func TestCreateTestCaseConcurrentOrdinalsAreDistinct(t *testing.T) {
	forEachStore(t, func(t *testing.T, s Store) {
		p, _ := mustProblem(t, s, "conc")
		const n = 20
		var (
			wg       sync.WaitGroup
			mu       sync.Mutex
			ordinals []int
		)
		for range n {
			wg.Add(1)
			go func() {
				defer wg.Done()
				tc, err := s.CreateTestCase(context.Background(), TestCase{ProblemID: p.ID, Input: "x"})
				if err != nil {
					t.Error(err)
					return
				}
				mu.Lock()
				ordinals = append(ordinals, tc.Ordinal)
				mu.Unlock()
			}()
		}
		wg.Wait()
		sort.Ints(ordinals)
		for i, o := range ordinals {
			if o != i+1 {
				t.Fatalf("ordinals not 1..%d: %v", n, ordinals)
			}
		}
	})
}

func TestCreateSubmissionDefaults(t *testing.T) {
	forEachStore(t, func(t *testing.T, s Store) {
		ctx := context.Background()
		p, _ := mustProblem(t, s, "p")
		sub, err := s.CreateSubmission(ctx, Submission{
			ProblemID: p.ID, Username: "bob", Language: LanguageCPP, Source: "int main(){}",
			Status: StatusFinished, Verdict: VerdictAccepted, Passed: 3, Results: []TestResult{{Test: 1}},
		})
		if err != nil {
			t.Fatal(err)
		}
		if sub.Status != StatusPending || sub.Verdict != VerdictNone || sub.Passed != 0 ||
			len(sub.Results) != 0 || sub.Results == nil || sub.CreatedAt.IsZero() || !sub.CreatedAt.Equal(sub.UpdatedAt) {
			t.Fatalf("unexpected defaults: %+v", sub)
		}
		got, err := s.GetSubmission(ctx, sub.ID)
		if err != nil || got.Source != "int main(){}" || got.Language != LanguageCPP || got.Username != "bob" {
			t.Fatalf("get: %+v, %v", got, err)
		}
		if _, err := s.CreateSubmission(ctx, Submission{ProblemID: 999, Language: LanguageC, Source: "x"}); !errors.Is(err, ErrNotFound) {
			t.Fatalf("want ErrNotFound, got %v", err)
		}
	})
}

func TestListSubmissionsFilters(t *testing.T) {
	forEachStore(t, func(t *testing.T, s Store) {
		ctx := context.Background()
		p1, _ := mustProblem(t, s, "p1")
		p2, _ := mustProblem(t, s, "p2")
		a := mustSubmission(t, s, p1.ID, "alice")
		time.Sleep(2 * time.Millisecond)
		b := mustSubmission(t, s, p1.ID, "bob")
		time.Sleep(2 * time.Millisecond)
		c := mustSubmission(t, s, p2.ID, "alice")
		if _, err := s.UpdateSubmission(ctx, b.ID, SubmissionUpdate{Status: ptr(StatusJudging)}); err != nil {
			t.Fatal(err)
		}
		if _, err := s.UpdateSubmission(ctx, c.ID, SubmissionUpdate{Status: ptr(StatusFinished)}); err != nil {
			t.Fatal(err)
		}

		ids := func(f SubmissionFilter) []int64 {
			t.Helper()
			subs, err := s.ListSubmissions(ctx, f)
			if err != nil {
				t.Fatal(err)
			}
			out := []int64{}
			for _, x := range subs {
				out = append(out, x.ID)
			}
			return out
		}
		check := func(name string, f SubmissionFilter, want ...int64) {
			t.Helper()
			got := ids(f)
			if len(got) != len(want) {
				t.Fatalf("%s: got %v, want %v", name, got, want)
			}
			for i := range got {
				if got[i] != want[i] {
					t.Fatalf("%s: got %v, want %v", name, got, want)
				}
			}
		}
		check("all newest first", SubmissionFilter{}, c.ID, b.ID, a.ID)
		check("problem", SubmissionFilter{ProblemID: p1.ID}, b.ID, a.ID)
		check("username", SubmissionFilter{Username: "alice"}, c.ID, a.ID)
		check("statuses any-of", SubmissionFilter{Statuses: []string{StatusPending, StatusJudging}}, b.ID, a.ID)
		check("single status", SubmissionFilter{Statuses: []string{StatusFinished}}, c.ID)
		check("combined", SubmissionFilter{ProblemID: p1.ID, Username: "alice", Statuses: []string{StatusPending}}, a.ID)
		check("limit", SubmissionFilter{Limit: 1}, c.ID)
		check("offset", SubmissionFilter{Limit: 1, Offset: 1}, b.ID)
		check("offset past end", SubmissionFilter{Offset: 10})

		// updated_before is strict: a's update time is earlier than b's.
		a, _ = s.GetSubmission(ctx, a.ID)
		b, _ = s.GetSubmission(ctx, b.ID)
		if !a.UpdatedAt.Before(b.UpdatedAt) {
			t.Fatalf("expected a.UpdatedAt < b.UpdatedAt: %v %v", a.UpdatedAt, b.UpdatedAt)
		}
		check("updated_before", SubmissionFilter{UpdatedBefore: b.UpdatedAt}, a.ID)
		check("updated_before far future", SubmissionFilter{UpdatedBefore: time.Now().Add(time.Hour)}, c.ID, b.ID, a.ID)
	})
}

func TestListSubmissionsDefaultLimit(t *testing.T) {
	forEachStore(t, func(t *testing.T, s Store) {
		p, _ := mustProblem(t, s, "many")
		for range DefaultListLimit + 5 {
			mustSubmission(t, s, p.ID, "u")
		}
		subs, err := s.ListSubmissions(context.Background(), SubmissionFilter{})
		if err != nil || len(subs) != DefaultListLimit {
			t.Fatalf("want %d, got %d (%v)", DefaultListLimit, len(subs), err)
		}
	})
}

func TestUpdateSubmissionPartial(t *testing.T) {
	forEachStore(t, func(t *testing.T, s Store) {
		ctx := context.Background()
		p, _ := mustProblem(t, s, "upd")
		sub := mustSubmission(t, s, p.ID, "alice")
		time.Sleep(2 * time.Millisecond)

		results := []TestResult{
			{Test: 1, Verdict: VerdictAccepted, TimeMs: 12, MemoryKb: 9000, Sample: true},
			{Test: 2, Verdict: VerdictWrongAnswer, TimeMs: 3, MemoryKb: 1},
		}
		upd, err := s.UpdateSubmission(ctx, sub.ID, SubmissionUpdate{
			Status: ptr(StatusFinished), Verdict: ptr(VerdictWrongAnswer), Passed: ptr(1), Total: ptr(2),
			TimeMs: ptr(12), Message: ptr("Wrong Answer on test 2"), Results: &results,
		})
		if err != nil {
			t.Fatal(err)
		}
		if upd.Status != StatusFinished || upd.Verdict != VerdictWrongAnswer || upd.Passed != 1 || upd.Total != 2 ||
			upd.TimeMs != 12 || upd.Message != "Wrong Answer on test 2" || len(upd.Results) != 2 ||
			upd.Results[0] != results[0] || upd.Results[1] != results[1] ||
			upd.Language != LanguagePython || upd.Source != "print(1)" {
			t.Fatalf("update not applied: %+v", upd)
		}
		if !upd.UpdatedAt.After(sub.UpdatedAt) || !upd.CreatedAt.Equal(sub.CreatedAt) {
			t.Fatalf("timestamps: created %v->%v updated %v->%v", sub.CreatedAt, upd.CreatedAt, sub.UpdatedAt, upd.UpdatedAt)
		}

		// Empty update: only updated_at moves; nil results keep the old ones.
		time.Sleep(2 * time.Millisecond)
		again, err := s.UpdateSubmission(ctx, sub.ID, SubmissionUpdate{})
		if err != nil || again.Verdict != VerdictWrongAnswer || len(again.Results) != 2 || !again.UpdatedAt.After(upd.UpdatedAt) {
			t.Fatalf("empty update: %+v, %v", again, err)
		}
		// Empty slice clears results.
		cleared, err := s.UpdateSubmission(ctx, sub.ID, SubmissionUpdate{Results: &[]TestResult{}})
		if err != nil || len(cleared.Results) != 0 || cleared.Results == nil {
			t.Fatalf("clear: %+v, %v", cleared, err)
		}
		if _, err := s.UpdateSubmission(ctx, 999, SubmissionUpdate{Status: ptr(StatusJudging)}); !errors.Is(err, ErrNotFound) {
			t.Fatalf("want ErrNotFound, got %v", err)
		}
	})
}

func TestUpdateSubmissionCompareAndSet(t *testing.T) {
	forEachStore(t, func(t *testing.T, s Store) {
		ctx := context.Background()
		p, _ := mustProblem(t, s, "cas")
		sub := mustSubmission(t, s, p.ID, "alice")

		got, err := s.UpdateSubmission(ctx, sub.ID, SubmissionUpdate{
			Status: ptr(StatusJudging), ExpectedStatuses: []string{StatusPending},
		})
		if err != nil || got.Status != StatusJudging {
			t.Fatalf("matching CAS: %+v, %v", got, err)
		}
		got, err = s.UpdateSubmission(ctx, sub.ID, SubmissionUpdate{
			Status: ptr(StatusFinished), Verdict: ptr(VerdictAccepted),
			ExpectedStatuses: []string{StatusPending, StatusJudging},
		})
		if err != nil || got.Status != StatusFinished {
			t.Fatalf("any-of CAS: %+v, %v", got, err)
		}
		// A late duplicate result must not overwrite the finished submission.
		_, err = s.UpdateSubmission(ctx, sub.ID, SubmissionUpdate{
			Status: ptr(StatusFailed), Verdict: ptr(VerdictInternalError),
			ExpectedStatuses: []string{StatusPending, StatusJudging},
		})
		if !errors.Is(err, ErrPrecondition) {
			t.Fatalf("want ErrPrecondition, got %v", err)
		}
		cur, _ := s.GetSubmission(ctx, sub.ID)
		if cur.Status != StatusFinished || cur.Verdict != VerdictAccepted || !cur.UpdatedAt.Equal(got.UpdatedAt) {
			t.Fatalf("failed CAS changed the row: %+v", cur)
		}
		if _, err := s.UpdateSubmission(ctx, 999, SubmissionUpdate{ExpectedStatuses: []string{StatusPending}}); !errors.Is(err, ErrNotFound) {
			t.Fatalf("missing id with CAS: want ErrNotFound, got %v", err)
		}
	})
}

func TestUpdateSubmissionCASIsAtomic(t *testing.T) {
	forEachStore(t, func(t *testing.T, s Store) {
		p, _ := mustProblem(t, s, "race")
		sub := mustSubmission(t, s, p.ID, "alice")
		const n = 20
		var (
			wg   sync.WaitGroup
			mu   sync.Mutex
			wins int
		)
		for range n {
			wg.Add(1)
			go func() {
				defer wg.Done()
				_, err := s.UpdateSubmission(context.Background(), sub.ID, SubmissionUpdate{
					Status: ptr(StatusJudging), ExpectedStatuses: []string{StatusPending},
				})
				switch {
				case err == nil:
					mu.Lock()
					wins++
					mu.Unlock()
				case !errors.Is(err, ErrPrecondition):
					t.Error(err)
				}
			}()
		}
		wg.Wait()
		if wins != 1 {
			t.Fatalf("exactly one CAS should win, got %d", wins)
		}
	})
}

package store

import (
	"context"
	"encoding/json"
	"sort"
	"sync"
	"time"
)

// Memory is a thread-safe in-memory Store. It is intended for tests and
// local development without a database.
type Memory struct {
	mu          sync.RWMutex
	problems    map[int64]Problem
	testCases   map[int64]TestCase
	submissions map[int64]Submission
	nextID      int64
}

func NewMemory() *Memory {
	return &Memory{
		problems:    map[int64]Problem{},
		testCases:   map[int64]TestCase{},
		submissions: map[int64]Submission{},
	}
}

func (m *Memory) id() int64 { m.nextID++; return m.nextID }

func (m *Memory) Ping(context.Context) error { return nil }

func (m *Memory) ListProblems(context.Context) ([]Problem, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	out := make([]Problem, 0, len(m.problems))
	for _, p := range m.problems {
		out = append(out, p)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	return out, nil
}

func (m *Memory) GetProblem(_ context.Context, id int64) (Problem, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	p, ok := m.problems[id]
	if !ok {
		return Problem{}, ErrNotFound
	}
	return p, nil
}

func (m *Memory) slugTaken(slug string, exceptID int64) bool {
	for _, p := range m.problems {
		if p.Slug == slug && p.ID != exceptID {
			return true
		}
	}
	return false
}

func (m *Memory) CreateProblem(_ context.Context, p Problem) (Problem, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.slugTaken(p.Slug, 0) {
		return Problem{}, ErrConflict
	}
	p.ID = m.id()
	p.CreatedAt = time.Now().UTC()
	m.problems[p.ID] = p
	return p, nil
}

func (m *Memory) UpdateProblem(_ context.Context, p Problem) (Problem, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	old, ok := m.problems[p.ID]
	if !ok {
		return Problem{}, ErrNotFound
	}
	if m.slugTaken(p.Slug, p.ID) {
		return Problem{}, ErrConflict
	}
	p.CreatedAt = old.CreatedAt
	m.problems[p.ID] = p
	return p, nil
}

func (m *Memory) DeleteProblem(_ context.Context, id int64) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.problems[id]; !ok {
		return ErrNotFound
	}
	delete(m.problems, id)
	for k, tc := range m.testCases {
		if tc.ProblemID == id {
			delete(m.testCases, k)
		}
	}
	for k, s := range m.submissions {
		if s.ProblemID == id {
			delete(m.submissions, k)
		}
	}
	return nil
}

func (m *Memory) ListTestCases(_ context.Context, problemID int64, samplesOnly bool) ([]TestCase, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	if _, ok := m.problems[problemID]; !ok {
		return nil, ErrNotFound
	}
	out := []TestCase{}
	for _, tc := range m.testCases {
		if tc.ProblemID == problemID && (!samplesOnly || tc.IsSample) {
			out = append(out, tc)
		}
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Ordinal != out[j].Ordinal {
			return out[i].Ordinal < out[j].Ordinal
		}
		return out[i].ID < out[j].ID
	})
	return out, nil
}

func (m *Memory) CreateTestCase(_ context.Context, tc TestCase) (TestCase, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.problems[tc.ProblemID]; !ok {
		return TestCase{}, ErrNotFound
	}
	tc.ID = m.id()
	m.testCases[tc.ID] = tc
	return tc, nil
}

func (m *Memory) DeleteTestCase(_ context.Context, problemID, id int64) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	tc, ok := m.testCases[id]
	if !ok || tc.ProblemID != problemID {
		return ErrNotFound
	}
	delete(m.testCases, id)
	return nil
}

func (m *Memory) CreateSubmission(_ context.Context, s Submission) (Submission, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.problems[s.ProblemID]; !ok {
		return Submission{}, ErrNotFound
	}
	s.ID = m.id()
	if s.Status == "" {
		s.Status = StatusPending
	}
	if len(s.Results) == 0 {
		s.Results = json.RawMessage("[]")
	}
	now := time.Now().UTC()
	s.CreatedAt, s.UpdatedAt = now, now
	m.submissions[s.ID] = s
	return s, nil
}

func (m *Memory) GetSubmission(_ context.Context, id int64) (Submission, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	s, ok := m.submissions[id]
	if !ok {
		return Submission{}, ErrNotFound
	}
	return s, nil
}

func (m *Memory) ListSubmissions(_ context.Context, f SubmissionFilter) ([]Submission, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	out := []Submission{}
	for _, s := range m.submissions {
		if f.ProblemID != 0 && s.ProblemID != f.ProblemID {
			continue
		}
		if f.Username != "" && s.Username != f.Username {
			continue
		}
		if f.Status != "" && s.Status != f.Status {
			continue
		}
		out = append(out, s)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID > out[j].ID })
	if f.Offset >= len(out) {
		return []Submission{}, nil
	}
	out = out[f.Offset:]
	if f.Limit > 0 && f.Limit < len(out) {
		out = out[:f.Limit]
	}
	return out, nil
}

func (m *Memory) UpdateSubmission(_ context.Context, id int64, u SubmissionUpdate) (Submission, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	s, ok := m.submissions[id]
	if !ok {
		return Submission{}, ErrNotFound
	}
	if u.Status != nil {
		s.Status = *u.Status
	}
	if u.Verdict != nil {
		s.Verdict = *u.Verdict
	}
	if u.Passed != nil {
		s.Passed = *u.Passed
	}
	if u.Total != nil {
		s.Total = *u.Total
	}
	if u.TimeMs != nil {
		s.TimeMs = *u.TimeMs
	}
	if u.Message != nil {
		s.Message = *u.Message
	}
	if u.Results != nil {
		s.Results = *u.Results
	}
	s.UpdatedAt = time.Now().UTC()
	m.submissions[id] = s
	return s, nil
}

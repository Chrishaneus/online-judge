package gateway

import (
	"testing"
	"time"
)

type fakeClock struct{ t time.Time }

func (c *fakeClock) now() time.Time          { return c.t }
func (c *fakeClock) advance(d time.Duration) { c.t = c.t.Add(d) }

func newTestLimiter(perMin, burst int) (*RateLimiter, *fakeClock) {
	clk := &fakeClock{t: time.Unix(1_700_000_000, 0)}
	l := NewRateLimiter(perMin, burst)
	l.now = clk.now
	l.lastSweep = clk.t
	return l, clk
}

func TestBurstThenDeny(t *testing.T) {
	l, _ := newTestLimiter(60, 3)
	for i := 0; i < 3; i++ {
		if ok, _ := l.Allow("a"); !ok {
			t.Fatalf("request %d should pass", i)
		}
	}
	ok, wait := l.Allow("a")
	if ok {
		t.Fatal("4th request should be limited")
	}
	if wait <= 0 || wait > time.Second {
		t.Fatalf("unexpected retry-after %v", wait)
	}
}

func TestRefill(t *testing.T) {
	l, clk := newTestLimiter(60, 1) // 1 token / second
	l.Allow("a")
	if ok, _ := l.Allow("a"); ok {
		t.Fatal("should be empty")
	}
	clk.advance(1100 * time.Millisecond)
	if ok, _ := l.Allow("a"); !ok {
		t.Fatal("should have refilled")
	}
}

func TestKeysAreIndependent(t *testing.T) {
	l, _ := newTestLimiter(60, 1)
	l.Allow("a")
	if ok, _ := l.Allow("b"); !ok {
		t.Fatal("other client must not be affected")
	}
}

func TestSweepDropsIdleBuckets(t *testing.T) {
	l, clk := newTestLimiter(60, 1)
	l.Allow("a")
	l.Allow("b")
	clk.advance(idleTTL + time.Minute)
	l.Allow("c")
	if n := l.size(); n != 1 {
		t.Fatalf("expected only the fresh bucket, have %d", n)
	}
}

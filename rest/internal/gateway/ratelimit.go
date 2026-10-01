package gateway

import (
	"math"
	"sync"
	"time"
)

// RateLimiter is a keyed token-bucket limiter (one bucket per client).
type RateLimiter struct {
	mu        sync.Mutex
	buckets   map[string]*bucket
	perSecond float64
	burst     float64
	now       func() time.Time
	lastSweep time.Time
}

type bucket struct {
	tokens float64
	last   time.Time
}

// idleTTL is how long an untouched bucket is kept; a full bucket is
// indistinguishable from a missing one, so dropping it is lossless.
const idleTTL = 10 * time.Minute

func NewRateLimiter(perMinute, burst int) *RateLimiter {
	if burst < 1 {
		burst = 1
	}
	return &RateLimiter{
		buckets:   map[string]*bucket{},
		perSecond: float64(perMinute) / 60,
		burst:     float64(burst),
		now:       time.Now,
	}
}

// Allow consumes a token for key. When denied it returns how long the
// client should wait before retrying.
func (l *RateLimiter) Allow(key string) (bool, time.Duration) {
	l.mu.Lock()
	defer l.mu.Unlock()
	now := l.now()
	l.sweep(now)

	b, ok := l.buckets[key]
	if !ok {
		b = &bucket{tokens: l.burst, last: now}
		l.buckets[key] = b
	}
	b.tokens = math.Min(l.burst, b.tokens+now.Sub(b.last).Seconds()*l.perSecond)
	b.last = now
	if b.tokens >= 1 {
		b.tokens--
		return true, 0
	}
	if l.perSecond <= 0 {
		return false, time.Hour
	}
	wait := time.Duration((1 - b.tokens) / l.perSecond * float64(time.Second))
	return false, wait
}

func (l *RateLimiter) sweep(now time.Time) {
	if now.Sub(l.lastSweep) < time.Minute {
		return
	}
	l.lastSweep = now
	for k, b := range l.buckets {
		if now.Sub(b.last) > idleTTL {
			delete(l.buckets, k)
		}
	}
}

func (l *RateLimiter) size() int {
	l.mu.Lock()
	defer l.mu.Unlock()
	return len(l.buckets)
}

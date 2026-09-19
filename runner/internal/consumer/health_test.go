package consumer

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestHealthFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "healthy")
	if err := CheckHealth(path, 20*time.Second); err == nil {
		t.Fatal("missing file must be unhealthy")
	}
	c := New(Config{HealthFile: path}, &Handler{Log: quietLog()})
	c.touchHealth()
	if err := CheckHealth(path, 20*time.Second); err != nil {
		t.Fatalf("fresh heartbeat should be healthy: %v", err)
	}
	old := time.Now().Add(-21 * time.Second)
	if err := os.Chtimes(path, old, old); err != nil {
		t.Fatal(err)
	}
	if err := CheckHealth(path, 20*time.Second); err == nil {
		t.Fatal("stale heartbeat must be unhealthy")
	}
}

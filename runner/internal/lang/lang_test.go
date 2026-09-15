package lang

import "testing"

func TestRegistry(t *testing.T) {
	for _, id := range []string{"python", "c", "cpp", "javascript"} {
		l, ok := Get(id)
		if !ok {
			t.Fatalf("language %q missing", id)
		}
		if l.SourceFile == "" || len(l.RunArgs(128)) == 0 {
			t.Fatalf("language %q incomplete: %+v", id, l)
		}
	}
	if _, ok := Get("cobol"); ok {
		t.Fatal("unexpected language cobol")
	}
	if got := len(All()); got != 4 {
		t.Fatalf("All() = %d languages, want 4", got)
	}
}

func TestNodeMemoryFlag(t *testing.T) {
	l, _ := Get("javascript")
	args := l.RunArgs(256)
	if args[1] != "--max-old-space-size=256" {
		t.Fatalf("unexpected args %v", args)
	}
}

func TestRunArgsAreCopies(t *testing.T) {
	l, _ := Get("python")
	a := l.RunArgs(1)
	a[0] = "mutated"
	if l.RunArgs(1)[0] != "python3" {
		t.Fatal("RunArgs must return a fresh slice")
	}
}

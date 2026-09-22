// Package lang describes how to compile and run each supported language.
package lang

import (
	"fmt"
	"sort"
)

type Language struct {
	ID   string `json:"id"`
	Name string `json:"name"`

	// SourceFile is the file name the submission is written to.
	SourceFile string `json:"-"`
	// Compile is the compile/check command; nil means no compile step.
	Compile []string `json:"-"`
	// LimitAddressSpace controls whether RLIMIT_AS is applied when running.
	// Runtimes that reserve large virtual ranges up front (V8) must not have it.
	LimitAddressSpace bool `json:"-"`

	run func(memoryMB int) []string
}

// RunArgs returns the command used to execute the compiled program.
func (l Language) RunArgs(memoryMB int) []string { return l.run(memoryMB) }

func fixed(args ...string) func(int) []string {
	return func(int) []string { return append([]string(nil), args...) }
}

var registry = map[string]Language{
	"python": {
		ID: "python", Name: "Python 3",
		SourceFile:        "main.py",
		Compile:           []string{"python3", "-m", "py_compile", "main.py"},
		LimitAddressSpace: true,
		run:               fixed("python3", "-B", "main.py"),
	},
	"c": {
		ID: "c", Name: "C17 (gcc)",
		SourceFile:        "main.c",
		Compile:           []string{"gcc", "-O2", "-std=c17", "-pipe", "-o", "main", "main.c", "-lm"},
		LimitAddressSpace: true,
		run:               fixed("./main"),
	},
	"cpp": {
		ID: "cpp", Name: "C++17 (g++)",
		SourceFile:        "main.cpp",
		Compile:           []string{"g++", "-O2", "-std=c++17", "-pipe", "-o", "main", "main.cpp"},
		LimitAddressSpace: true,
		run:               fixed("./main"),
	},
	"javascript": {
		ID: "javascript", Name: "JavaScript (Node.js)",
		SourceFile: "main.js",
		Compile:    []string{"node", "--check", "main.js"},
		run: func(memoryMB int) []string {
			return []string{"node", fmt.Sprintf("--max-old-space-size=%d", memoryMB), "main.js"}
		},
	},
}

// Get looks up a language by id.
func Get(id string) (Language, bool) {
	l, ok := registry[id]
	return l, ok
}

// All returns every supported language sorted by id.
func All() []Language {
	out := make([]Language, 0, len(registry))
	for _, l := range registry {
		out = append(out, l)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	return out
}

package consumer

import (
	"fmt"

	"github.com/online-judge/oj-runner/internal/executor"
	ojv1 "github.com/online-judge/oj-runner/internal/gen/oj/v1"
)

// languageIDs maps the contract's Language enum to lang registry ids.
var languageIDs = map[ojv1.Language]string{
	ojv1.Language_LANGUAGE_PYTHON:     "python",
	ojv1.Language_LANGUAGE_C:          "c",
	ojv1.Language_LANGUAGE_CPP:        "cpp",
	ojv1.Language_LANGUAGE_JAVASCRIPT: "javascript",
}

// LanguageID returns the lang registry id for l; false for UNSPECIFIED and
// values this runner does not know.
func LanguageID(l ojv1.Language) (string, bool) {
	id, ok := languageIDs[l]
	return id, ok
}

var runStatuses = map[string]ojv1.RunStatus{
	executor.StatusOK:  ojv1.RunStatus_RUN_STATUS_OK,
	executor.StatusTLE: ojv1.RunStatus_RUN_STATUS_TIME_LIMIT_EXCEEDED,
	executor.StatusMLE: ojv1.RunStatus_RUN_STATUS_MEMORY_LIMIT_EXCEEDED,
	executor.StatusOLE: ojv1.RunStatus_RUN_STATUS_OUTPUT_LIMIT_EXCEEDED,
	executor.StatusRE:  ojv1.RunStatus_RUN_STATUS_RUNTIME_ERROR,
}

// ToResult converts an executor response into the contract's ExecuteResult.
//
// maxOutput bounds the total stdout+stderr bytes in the result so the event
// fits in one AMQP message. Once it is used up, the remaining tests keep
// their metrics but lose their output and are reported as
// OUTPUT_LIMIT_EXCEEDED (unless they already failed otherwise).
func ToResult(resp executor.Response, maxOutput int) (*ojv1.ExecuteResult, error) {
	switch resp.Status {
	case executor.StatusCE:
		return &ojv1.ExecuteResult{
			Status:        ojv1.ExecuteStatus_EXECUTE_STATUS_COMPILATION_ERROR,
			CompileOutput: resp.CompileOutput,
		}, nil
	case executor.StatusOK:
	default:
		return nil, fmt.Errorf("unknown executor status %q", resp.Status)
	}

	out := &ojv1.ExecuteResult{
		Status:        ojv1.ExecuteStatus_EXECUTE_STATUS_OK,
		CompileOutput: resp.CompileOutput,
		Results:       make([]*ojv1.TestRun, 0, len(resp.Results)),
	}
	budget := maxOutput
	for _, r := range resp.Results {
		status, ok := runStatuses[r.Status]
		if !ok {
			return nil, fmt.Errorf("unknown test status %q for test %q", r.Status, r.ID)
		}
		run := &ojv1.TestRun{
			Id:       r.ID,
			Status:   status,
			Stdout:   r.Stdout,
			Stderr:   r.Stderr,
			ExitCode: int32(r.ExitCode),
			TimeMs:   int32(r.TimeMs),
			MemoryKb: r.MemoryKB,
		}
		if size := len(r.Stdout) + len(r.Stderr); size > budget {
			budget = 0
			run.Stdout, run.Stderr = "", ""
			if status == ojv1.RunStatus_RUN_STATUS_OK {
				run.Status = ojv1.RunStatus_RUN_STATUS_OUTPUT_LIMIT_EXCEEDED
			}
		} else {
			budget -= size
		}
		out.Results = append(out.Results, run)
	}
	return out, nil
}

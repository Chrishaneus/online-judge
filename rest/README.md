# rest

Public REST API (edge gateway) of the Online Judge, written in Go.

It is the only backend service exposed to clients. Each `/api/v1` route is
translated into one call of midlayer's gRPC API (`oj.v1.JudgeService`,
defined in [proto](../proto)), and rest adds the cross-cutting
concerns:

* versioned routes under `/api/v1`, served as **canonical proto JSON**
* **admin authentication** with a bearer token (`ADMIN_TOKEN`); admin routes
  are disabled when no token is configured
* **per-client rate limiting** (token bucket) for code-executing endpoints
* **CORS**
* `X-Request-ID` generation, forwarded to the midlayer as `x-request-id`
  gRPC metadata (`Authorization` and cookies are never forwarded)
* request body size limits, path/query parameter validation, per-call
  gRPC deadlines
* panic recovery and structured JSON access logs

There is no business logic here: validation of the request *content* and all
judging rules live in midlayer.

## JSON

Bodies and responses are the RPC request/response messages from
`proto/oj/v1/judge.proto` in canonical proto JSON:

* camelCase field names (`problemId`, `timeLimitMs`); snake_case is also
  accepted in request bodies
* enums by name (`"LANGUAGE_PYTHON"`, `"VERDICT_ACCEPTED"`)
* int64 fields as strings (`"id": "42"`); numbers are accepted on input
* Timestamps as RFC 3339 (`"2026-01-02T03:04:05Z"`)
* responses contain every field, with defaults (`0`, `""`, `[]`, `null` for
  unset messages)

Unknown fields in a request body are rejected with 400. Path parameters
replace the matching body fields (e.g. `id` on `PUT /admin/problems/{id}`).

## Endpoints

Public:

| Method | Path | RPC | Request → Response | Success |
|---|---|---|---|---|
| GET | `/api/v1/status` | `GetStatus` | `GetStatusRequest` → `GetStatusResponse` | 200 |
| GET | `/api/v1/languages` | `ListLanguages` | `ListLanguagesRequest` → `ListLanguagesResponse` | 200 |
| GET | `/api/v1/problems` | `ListProblemSummaries` | `ListProblemSummariesRequest` → `ListProblemSummariesResponse` | 200 |
| GET | `/api/v1/problems/{id}` | `GetProblemDetail` | `GetProblemDetailRequest` → `GetProblemDetailResponse` | 200 |
| POST | `/api/v1/submissions` *(rate limited, 512 KiB)* | `Submit` | `SubmitRequest` → `SubmitResponse` | 202 |
| GET | `/api/v1/submissions?problemId=&username=&limit=&offset=` | `ListSubmissionSummaries` | `ListSubmissionSummariesRequest` → `ListSubmissionSummariesResponse` | 200 |
| GET | `/api/v1/submissions/{id}` | `GetSubmissionDetail` | `GetSubmissionDetailRequest` → `GetSubmissionDetailResponse` | 200 |
| POST | `/api/v1/run` *(rate limited, 2 MiB)* | `RunCode` | `RunCodeRequest` → `RunCodeResponse` | 200 |

`problem_id` is accepted as an alias of `problemId` in the submissions query.

Admin (`Authorization: Bearer $ADMIN_TOKEN`; bodies up to 64 MiB):

| Method | Path | RPC | Request → Response | Success |
|---|---|---|---|---|
| GET | `/api/v1/admin/verify` | *(local)* | → `{"admin": true}` | 200 |
| POST | `/api/v1/admin/problems` | `AddProblem` | `AddProblemRequest` → `AddProblemResponse` | 201 |
| PUT | `/api/v1/admin/problems/{id}` | `EditProblem` | `EditProblemRequest` → `EditProblemResponse` | 200 |
| DELETE | `/api/v1/admin/problems/{id}` | `RemoveProblem` | `RemoveProblemRequest` → *(no body)* | 204 |
| GET | `/api/v1/admin/problems/{problemId}/testcases` | `ListProblemTestCases` | `ListProblemTestCasesRequest` → `ListProblemTestCasesResponse` | 200 |
| POST | `/api/v1/admin/problems/{problemId}/testcases` | `AddTestCase` | `AddTestCaseRequest` → `AddTestCaseResponse` | 201 |
| DELETE | `/api/v1/admin/problems/{problemId}/testcases/{id}` | `RemoveTestCase` | `RemoveTestCaseRequest` → *(no body)* | 204 |

`GET /healthz` is the liveness probe; it never calls the midlayer.
`rest healthcheck` (used by the Docker `HEALTHCHECK`) calls it.

### Errors

Every non-2xx response is an `oj.v1.ErrorResponse`:

```json
{"error": "invalid JSON body", "details": ["proto: (line 1:2): unknown field \"bogus\""]}
```

| Cause | HTTP | `error` |
|---|---|---|
| unparsable body, unknown field, invalid path/query parameter | 400 | describes the problem |
| missing / wrong admin token | 401 (403 when admin is disabled) | fixed message |
| body over the limit | 413 | `request body too large` |
| local rate limit (with `Retry-After`) | 429 | `rate limit exceeded, retry in Ns` |
| gRPC `INVALID_ARGUMENT` | 422 | midlayer's message |
| gRPC `NOT_FOUND` | 404 | midlayer's message |
| gRPC `ALREADY_EXISTS`, `FAILED_PRECONDITION` | 409 | midlayer's message |
| gRPC `RESOURCE_EXHAUSTED` (judging queue full) | 429 | midlayer's message |
| gRPC `DEADLINE_EXCEEDED` | 504 | `upstream timed out` |
| gRPC `UNAVAILABLE` | 503 | `service unavailable` |
| any other gRPC code | 502 | `upstream error` (details are logged, not returned) |

## Examples

```bash
API=http://localhost:8000/api/v1

curl -s $API/problems
curl -s $API/problems/1

# Submit: 202 with the PENDING submission; poll it for the verdict.
curl -s -X POST $API/submissions -H 'Content-Type: application/json' \
  -d '{"problemId":"1","language":"LANGUAGE_PYTHON","source":"print(sum(map(int, input().split())))","username":"ann"}'
curl -s $API/submissions/42
curl -s "$API/submissions?problemId=1&username=ann&limit=20"

# Custom run
curl -s -X POST $API/run -H 'Content-Type: application/json' \
  -d '{"language":"LANGUAGE_CPP","source":"#include <cstdio>\nint main(){puts(\"hi\");}","stdin":""}'

# Admin
AUTH="Authorization: Bearer $ADMIN_TOKEN"
curl -s -X POST $API/admin/problems -H "$AUTH" -H 'Content-Type: application/json' -d '{
  "slug": "a-plus-b", "title": "A + B", "statement": "Print a + b.",
  "difficulty": "DIFFICULTY_EASY", "timeLimitMs": 1000, "memoryLimitMb": 256,
  "testCases": [{"input": "1 2\n", "expectedOutput": "3\n", "isSample": true}]}'
curl -s -X PUT $API/admin/problems/1 -H "$AUTH" -d '{"slug":"a-plus-b","title":"A plus B","statement":"…","difficulty":"DIFFICULTY_EASY"}'
curl -s -X POST $API/admin/problems/1/testcases -H "$AUTH" -d '{"testCase":{"input":"5 7\n","expectedOutput":"12\n"}}'
curl -s -X DELETE $API/admin/problems/1/testcases/3 -H "$AUTH" -o /dev/null -w '%{http_code}\n'   # 204
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `REST_ADDR` | `:8000` | HTTP listen address |
| `MIDLAYER_ADDR` | `localhost:50051` (`midlayer:50051` in the image) | midlayer gRPC address (plaintext, internal network) |
| `UPSTREAM_TIMEOUT_S` | `60` | Deadline of each gRPC call |
| `RUN_TIMEOUT_S` | `60` | Deadline of `RunCode` (compile + run on a runner) |
| `ADMIN_TOKEN` | *(empty → admin off)* | Bearer token for admin routes (≥ 16 random characters) |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `RATE_LIMIT_PER_MIN` | `20` | Sustained submissions + runs per client per minute |
| `RATE_LIMIT_BURST` | `5` | Burst size |
| `TRUST_PROXY_HEADERS` | `false` | Use `X-Real-IP` / `X-Forwarded-For` for the client IP |

gRPC messages may be up to 64 MiB in both directions.

## Development

Requires Go 1.27 (the `go` command downloads it if needed).

```bash
make check                      # gofmt, go vet, go test
MIDLAYER_ADDR=localhost:50051 ADMIN_TOKEN=dev-token-0123456789 make run
make docker                     # online-judge/rest:latest
```

`internal/gen/oj/v1` is generated from proto (`make gen` at the repo root); never
edit it by hand.

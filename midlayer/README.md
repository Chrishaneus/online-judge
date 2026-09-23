# oj-midlayer

Business-logic layer of the Online Judge (Python / FastAPI).

Responsibilities:

* Orchestrates **judging**: a pool of async workers takes queued submissions,
  fetches the problem's test cases from **oj-dao**, executes the code on
  **oj-runner**, compares outputs, computes the verdict and stores it.
* Owns the **judging rules**: output normalisation (trailing whitespace and
  trailing blank lines are ignored; CRLF == LF) and verdict precedence.
* Shapes data for the public API: hidden test cases are never exposed, only
  samples; submission listings omit source code.
* Validates domain input (slugs, limits, supported languages, usernames).
* Recovers on restart: submissions left `PENDING`/`JUDGING` are re-queued.

It is an internal service. Authentication/authorisation and rate limiting
live in **oj-rest**.

## Verdicts

| Verdict | Meaning                         |
|---------|---------------------------------|
| `AC`    | Accepted                        |
| `WA`    | Wrong answer                    |
| `TLE`   | Time limit exceeded             |
| `MLE`   | Memory limit exceeded           |
| `OLE`   | Output limit exceeded           |
| `RE`    | Runtime error                   |
| `CE`    | Compilation error               |
| `IE`    | Internal error (judge failure)  |

The overall verdict is the verdict of the first failing test, else `AC`.

## Configuration

| Variable              | Default                 | Description                                     |
|-----------------------|-------------------------|-------------------------------------------------|
| `DAO_URL`             | `http://localhost:8001` | oj-dao base URL                                 |
| `RUNNER_URL`          | `http://localhost:8002` | oj-runner base URL or `unix:///path/to.sock`    |
| `JUDGE_WORKERS`       | `4`                     | Concurrent judging tasks                        |
| `RUNNER_TIMEOUT_S`    | `600`                   | Timeout for a single runner call                |

## API (internal)

| Method | Path                               | Description                                  |
|--------|------------------------------------|----------------------------------------------|
| GET    | `/healthz`                         | Health of this service and its dependencies |
| GET    | `/languages`                       | Supported languages                          |
| GET    | `/problems`                        | Problem summaries                            |
| GET    | `/problems/{id}`                   | Problem with statement and samples           |
| POST   | `/problems`                        | Create problem with test cases               |
| PUT    | `/problems/{id}`                   | Update problem metadata                      |
| DELETE | `/problems/{id}`                   | Delete problem                               |
| GET    | `/problems/{id}/testcases`         | All test cases (admin)                       |
| POST   | `/problems/{id}/testcases`         | Add test case (admin)                        |
| DELETE | `/problems/{id}/testcases/{tcid}`  | Delete test case (admin)                     |
| POST   | `/submissions`                     | Submit code (queued for judging)             |
| GET    | `/submissions`                     | List (`problem_id`, `username`, `limit`, `offset`) |
| GET    | `/submissions/{id}`                | Submission detail incl. per-test results     |
| POST   | `/run`                             | Run code against custom input (no judging)   |

## Development

```bash
uv venv && uv pip install -r requirements-dev.txt
.venv/bin/pytest
.venv/bin/uvicorn app.main:app --reload --port 8003
```

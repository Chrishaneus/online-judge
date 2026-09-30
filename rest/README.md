# oj-rest

Public REST API (edge gateway) of the Online Judge, written in Go with only
the standard library.

It is the only backend service exposed to clients. It forwards an explicit
allowlist of routes to **oj-midlayer** and adds the cross-cutting concerns:

* versioned routes under `/api/v1`
* **admin authentication** with a bearer token (`ADMIN_TOKEN`); admin routes
  are disabled when no token is configured
* **per-client rate limiting** (token bucket) for code-executing endpoints
* **CORS**
* `X-Request-ID` generation and propagation
* request body size limits and path parameter validation
* panic recovery and structured JSON access logs

## Endpoints

Public:

| Method | Path                           |
|--------|--------------------------------|
| GET    | `/api/v1/status`               |
| GET    | `/api/v1/languages`            |
| GET    | `/api/v1/problems`             |
| GET    | `/api/v1/problems/{id}`        |
| GET    | `/api/v1/submissions`          |
| GET    | `/api/v1/submissions/{id}`     |
| POST   | `/api/v1/submissions` *(rate limited)* |
| POST   | `/api/v1/run` *(rate limited)*         |

Admin (`Authorization: Bearer $ADMIN_TOKEN`):

| Method | Path                                             |
|--------|--------------------------------------------------|
| GET    | `/api/v1/admin/verify`                           |
| POST   | `/api/v1/admin/problems`                         |
| PUT    | `/api/v1/admin/problems/{id}`                    |
| DELETE | `/api/v1/admin/problems/{id}`                    |
| GET    | `/api/v1/admin/problems/{id}/testcases`          |
| POST   | `/api/v1/admin/problems/{id}/testcases`          |
| DELETE | `/api/v1/admin/problems/{id}/testcases/{tcid}`   |

`GET /healthz` is the liveness probe.

## Configuration

| Variable              | Default                  | Description                                          |
|-----------------------|--------------------------|------------------------------------------------------|
| `REST_ADDR`           | `:8000`                  | Listen address                                       |
| `MIDLAYER_URL`        | `http://localhost:8003`  | Upstream                                             |
| `ADMIN_TOKEN`         | *(empty → admin off)*    | Bearer token for admin routes                        |
| `CORS_ORIGINS`        | `*`                      | Comma-separated allowed origins                      |
| `RATE_LIMIT_PER_MIN`  | `20`                     | Sustained executions per client per minute           |
| `RATE_LIMIT_BURST`    | `5`                      | Burst size                                           |
| `TRUST_PROXY_HEADERS` | `false`                  | Use `X-Real-IP` / `X-Forwarded-For` for the client IP |

## Development

```bash
make test
MIDLAYER_URL=http://localhost:8003 ADMIN_TOKEN=dev make run
```

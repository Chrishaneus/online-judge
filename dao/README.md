# oj-dao

Repository (data access) service for the Online Judge.

It is the **only** component that talks to PostgreSQL. Every other service
reads and writes data through this service's internal HTTP API.

```
webapp -> rest -> midlayer -> dao -> postgres
                          \-> runner
```

## Configuration

| Variable       | Default | Description                                                    |
|----------------|---------|----------------------------------------------------------------|
| `DAO_ADDR`     | `:8001` | Listen address                                                 |
| `DATABASE_URL` | *(empty)* | PostgreSQL DSN. When empty an in-memory store is used (dev only) |

Migrations (including seed problems) are embedded in the binary and run on startup.

## API

| Method | Path                                   | Description                               |
|--------|----------------------------------------|-------------------------------------------|
| GET    | `/healthz`                             | Liveness + DB ping                        |
| GET    | `/problems`                            | List problems                             |
| POST   | `/problems`                            | Create problem                            |
| GET    | `/problems/{id}`                       | Get problem                               |
| PUT    | `/problems/{id}`                       | Update problem                            |
| DELETE | `/problems/{id}`                       | Delete problem (cascades)                 |
| GET    | `/problems/{id}/testcases`             | List test cases (`?samples_only=true`)    |
| POST   | `/problems/{id}/testcases`             | Add a test case                           |
| DELETE | `/problems/{id}/testcases/{tcid}`      | Delete a test case                        |
| GET    | `/submissions`                         | List (`?problem_id=&username=&limit=&offset=`) |
| POST   | `/submissions`                         | Create submission                         |
| GET    | `/submissions/{id}`                    | Get submission                            |
| PATCH  | `/submissions/{id}`                    | Partial update (status, verdict, results…) |

## Development

```bash
make test          # unit tests (in-memory store)
make run           # run locally with in-memory store
docker build -t oj-dao .
```

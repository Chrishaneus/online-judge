CREATE TABLE IF NOT EXISTS problems (
    id              BIGSERIAL PRIMARY KEY,
    slug            TEXT        NOT NULL UNIQUE,
    title           TEXT        NOT NULL,
    statement       TEXT        NOT NULL,
    difficulty      TEXT        NOT NULL DEFAULT 'easy',
    time_limit_ms   INT         NOT NULL DEFAULT 2000,
    memory_limit_mb INT         NOT NULL DEFAULT 256,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS test_cases (
    id              BIGSERIAL PRIMARY KEY,
    problem_id      BIGINT  NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    input           TEXT    NOT NULL,
    expected_output TEXT    NOT NULL,
    is_sample       BOOLEAN NOT NULL DEFAULT false,
    ordinal         INT     NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS test_cases_problem_idx ON test_cases(problem_id, ordinal);

CREATE TABLE IF NOT EXISTS submissions (
    id          BIGSERIAL PRIMARY KEY,
    problem_id  BIGINT      NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    username    TEXT        NOT NULL DEFAULT 'anonymous',
    language    TEXT        NOT NULL,
    source      TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'PENDING',
    verdict     TEXT        NOT NULL DEFAULT '',
    passed      INT         NOT NULL DEFAULT 0,
    total       INT         NOT NULL DEFAULT 0,
    time_ms     INT         NOT NULL DEFAULT 0,
    message     TEXT        NOT NULL DEFAULT '',
    results     JSONB       NOT NULL DEFAULT '[]'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS submissions_problem_idx  ON submissions(problem_id, id DESC);
CREATE INDEX IF NOT EXISTS submissions_username_idx ON submissions(username, id DESC);

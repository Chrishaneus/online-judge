-- Starter problems so a fresh deployment is immediately usable.

WITH p AS (
    INSERT INTO problems (slug, title, statement, difficulty, time_limit_ms, memory_limit_mb)
    VALUES ('a-plus-b', 'A + B',
'Read two integers **A** and **B** separated by whitespace and print their sum.

### Input
A single line containing two integers `A` and `B` (`-10^9 <= A, B <= 10^9`).

### Output
Print `A + B`.', 'easy', 1000, 128)
    ON CONFLICT (slug) DO NOTHING
    RETURNING id
)
INSERT INTO test_cases (problem_id, input, expected_output, is_sample, ordinal)
SELECT p.id, t.input, t.expected_output, t.is_sample, t.ordinal
FROM p, (VALUES
    ('1 2',                     '3',           true,  1),
    ('-5 5',                    '0',           true,  2),
    ('1000000000 1000000000',   '2000000000',  false, 3),
    ('-1000000000 -7',          '-1000000007', false, 4),
    ('123456 654321',           '777777',      false, 5)
) AS t(input, expected_output, is_sample, ordinal);

WITH p AS (
    INSERT INTO problems (slug, title, statement, difficulty, time_limit_ms, memory_limit_mb)
    VALUES ('reverse-string', 'Reverse a String',
'Given a single line of text, print it reversed.

### Input
One line `S` (`1 <= |S| <= 10^5`) consisting of printable ASCII characters without newlines.

### Output
Print `S` reversed.', 'easy', 1000, 128)
    ON CONFLICT (slug) DO NOTHING
    RETURNING id
)
INSERT INTO test_cases (problem_id, input, expected_output, is_sample, ordinal)
SELECT p.id, t.input, t.expected_output, t.is_sample, t.ordinal
FROM p, (VALUES
    ('hello',          'olleh',          true,  1),
    ('online judge',   'egduj enilno',   true,  2),
    ('a',              'a',              false, 3),
    ('racecar!',       '!racecar',       false, 4),
    ('Go and Python',  'nohtyP dna oG',  false, 5)
) AS t(input, expected_output, is_sample, ordinal);

WITH p AS (
    INSERT INTO problems (slug, title, statement, difficulty, time_limit_ms, memory_limit_mb)
    VALUES ('fibonacci', 'N-th Fibonacci Number',
'The Fibonacci sequence is defined as `F(0) = 0`, `F(1) = 1` and `F(n) = F(n-1) + F(n-2)`.

Given `N`, print `F(N)`.

### Input
A single integer `N` (`0 <= N <= 90`).

### Output
Print `F(N)`. The answer fits in a signed 64-bit integer.', 'medium', 1000, 128)
    ON CONFLICT (slug) DO NOTHING
    RETURNING id
)
INSERT INTO test_cases (problem_id, input, expected_output, is_sample, ordinal)
SELECT p.id, t.input, t.expected_output, t.is_sample, t.ordinal
FROM p, (VALUES
    ('0',  '0',                   true,  1),
    ('10', '55',                  true,  2),
    ('1',  '1',                   false, 3),
    ('50', '12586269025',         false, 4),
    ('90', '2880067194370816120', false, 5)
) AS t(input, expected_output, is_sample, ordinal);

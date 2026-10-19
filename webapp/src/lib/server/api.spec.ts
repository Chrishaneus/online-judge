import { describe, expect, it } from 'vitest';
import { Difficulty, Language, SubmissionStatus, Verdict } from '#lib/gen/oj/v1/types_pb.js';
import { CONTRACT_ERROR, createApi, parseId, toQuery } from './api.js';

interface Call {
	url: string;
	method: string;
	headers: Record<string, string>;
	body: unknown;
}

/** A fetch that records calls and answers with the given status / body / headers. */
function fakeFetch(status: number, body: unknown = {}, headers: Record<string, string> = {}) {
	const calls: Call[] = [];
	const fn = (async (input: RequestInfo | URL, init?: RequestInit) => {
		calls.push({
			url: String(input),
			method: init?.method ?? 'GET',
			headers: (init?.headers ?? {}) as Record<string, string>,
			body: init?.body ? JSON.parse(String(init.body)) : undefined
		});
		const text = typeof body === 'string' ? body : JSON.stringify(body);
		return new Response(status === 204 ? null : text, { status, headers });
	}) as typeof fetch;
	return { fn, calls };
}

const BASE = 'http://api:8000/api/v1/';

const problemJson = {
	id: '7',
	slug: 'a-plus-b',
	title: 'A + B',
	difficulty: 'DIFFICULTY_EASY',
	timeLimitMs: 1000,
	memoryLimitMb: 128
};

describe('createApi responses', () => {
	it('parses canonical proto JSON into typed messages', async () => {
		const { fn, calls } = fakeFetch(200, { problems: [problemJson] });
		const res = await createApi(BASE, fn).problems();

		expect(calls[0].url).toBe('http://api:8000/api/v1/problems');
		expect(res.ok).toBe(true);
		if (!res.ok) return;
		expect(res.data).toHaveLength(1);
		expect(res.data[0].id).toBe(7n);
		expect(res.data[0].difficulty).toBe(Difficulty.EASY);
		expect(res.data[0].timeLimitMs).toBe(1000);
	});

	it('ignores unknown fields (newer servers may add some)', async () => {
		const { fn } = fakeFetch(200, { problems: [{ ...problemJson, rating: 1200 }], next: 'x' });
		const res = await createApi(BASE, fn).problems();
		expect(res.ok).toBe(true);
	});

	it('maps unknown enum values (from a newer contract) to UNSPECIFIED', async () => {
		const { fn } = fakeFetch(200, {
			problems: [{ ...problemJson, difficulty: 'DIFFICULTY_INSANE' }]
		});
		const res = await createApi(BASE, fn).problems();
		expect(res.ok && res.data[0].difficulty).toBe(Difficulty.UNSPECIFIED);
	});

	it('reports a contract mismatch as 502', async () => {
		for (const body of [
			{ problems: 'nope' },
			{ problems: [{ ...problemJson, title: 42 }] },
			{ problems: [{ ...problemJson, id: 'seven' }] },
			'<html>not json</html>'
		]) {
			const { fn } = fakeFetch(200, body);
			expect(await createApi(BASE, fn).problems()).toEqual({
				ok: false,
				status: 502,
				error: CONTRACT_ERROR
			});
		}
	});

	it('treats a missing required sub-message as a contract mismatch', async () => {
		const { fn } = fakeFetch(200, {});
		const res = await createApi(BASE, fn).submission(1n);
		expect(res).toEqual({ ok: false, status: 502, error: CONTRACT_ERROR });
	});

	it('parses submissions with enums, int64 strings and timestamps', async () => {
		const { fn } = fakeFetch(200, {
			submission: {
				id: '42',
				problemId: '7',
				username: 'alice',
				language: 'LANGUAGE_PYTHON',
				status: 'SUBMISSION_STATUS_FINISHED',
				verdict: 'VERDICT_WRONG_ANSWER',
				passed: 2,
				total: 5,
				results: [
					{ test: 1, verdict: 'VERDICT_ACCEPTED', timeMs: 3, memoryKb: '2048', sample: true }
				],
				createTime: '2026-11-05T10:00:00Z'
			}
		});
		const res = await createApi(BASE, fn).submission(42n);
		expect(res.ok).toBe(true);
		if (!res.ok) return;
		expect(res.data.language).toBe(Language.PYTHON);
		expect(res.data.status).toBe(SubmissionStatus.FINISHED);
		expect(res.data.verdict).toBe(Verdict.WRONG_ANSWER);
		expect(res.data.results[0].memoryKb).toBe(2048n);
		expect(res.data.createTime?.seconds).toBe(BigInt(Date.parse('2026-11-05T10:00:00Z') / 1000));
	});
});

describe('createApi errors', () => {
	it('uses ErrorResponse.error and details', async () => {
		const { fn } = fakeFetch(422, { error: 'invalid submission', details: ['source: empty'] });
		expect(await createApi(BASE, fn).problem(1)).toEqual({
			ok: false,
			status: 422,
			error: 'invalid submission: source: empty'
		});
	});

	it('falls back to a generic message for non-ErrorResponse bodies', async () => {
		const { fn } = fakeFetch(502, '<html>Bad Gateway</html>');
		const res = await createApi(BASE, fn).problem(1);
		expect(res).toEqual({ ok: false, status: 502, error: 'Request failed (HTTP 502)' });
	});

	it('explains rate limiting with Retry-After', async () => {
		const { fn } = fakeFetch(429, { error: 'rate limited' }, { 'Retry-After': '12' });
		const res = await createApi(BASE, fn).run({ language: Language.PYTHON, source: 'x' });
		expect(res).toEqual({ ok: false, status: 429, error: 'Too many requests. Try again in 12s.' });

		const { fn: fn2 } = fakeFetch(429, {});
		const res2 = await createApi(BASE, fn2).run({ language: Language.PYTHON, source: 'x' });
		expect(res2.ok || res2.error).toBe('Too many requests. Try again shortly.');
	});

	it('reports an unreachable API as 503', async () => {
		const failing = (async () => {
			throw new TypeError('fetch failed');
		}) as typeof fetch;
		expect(await createApi(BASE, failing).status()).toEqual({
			ok: false,
			status: 503,
			error: 'The judge is unreachable'
		});
	});
});

describe('createApi requests', () => {
	it('submits canonical proto JSON and forwards the visitor IP', async () => {
		const { fn, calls } = fakeFetch(200, {
			submission: { id: '9', problemId: '7', status: 'SUBMISSION_STATUS_PENDING' }
		});
		const res = await createApi(BASE, fn).submit(
			{ problemId: 7n, language: Language.CPP, source: 'int main(){}', username: 'bob' },
			'203.0.113.5'
		);

		expect(res.ok && res.data.id).toBe(9n);
		expect(calls[0]).toMatchObject({
			url: 'http://api:8000/api/v1/submissions',
			method: 'POST',
			headers: { 'Content-Type': 'application/json', 'X-Real-IP': '203.0.113.5' },
			body: { problemId: '7', language: 'LANGUAGE_CPP', source: 'int main(){}', username: 'bob' }
		});
	});

	it('runs code with the problem limits and the visitor IP', async () => {
		const { fn, calls } = fakeFetch(200, {
			status: 'RUN_STATUS_OK',
			stdout: '3\n',
			timeMs: 12,
			memoryKb: '9000'
		});
		const res = await createApi(BASE, fn).run(
			{ language: Language.PYTHON, source: 'print(3)', stdin: '1 2', problemId: 7n },
			'198.51.100.1'
		);
		expect(res.ok && res.data.stdout).toBe('3\n');
		expect(calls[0].url).toBe('http://api:8000/api/v1/run');
		expect(calls[0].headers['X-Real-IP']).toBe('198.51.100.1');
		expect(calls[0].body).toEqual({
			language: 'LANGUAGE_PYTHON',
			source: 'print(3)',
			stdin: '1 2',
			problemId: '7'
		});
	});

	it('does not send X-Real-IP or Authorization on public reads', async () => {
		const { fn, calls } = fakeFetch(200, { languages: [] });
		await createApi(BASE, fn).languages();
		expect(calls[0].headers['X-Real-IP']).toBeUndefined();
		expect(calls[0].headers.Authorization).toBeUndefined();
	});

	it('lists submissions with camelCase query parameters', async () => {
		const { fn, calls } = fakeFetch(200, { submissions: [] });
		await createApi(BASE, fn).submissions({
			problemId: 7n,
			username: 'alice',
			limit: 26,
			offset: 25
		});
		expect(calls[0].url).toBe(
			'http://api:8000/api/v1/submissions?problemId=7&username=alice&limit=26&offset=25'
		);

		await createApi(BASE, fn).submissions({ problemId: 0n, username: '', limit: 26, offset: 0 });
		expect(calls[1].url).toBe('http://api:8000/api/v1/submissions?limit=26');
	});

	it('sends the admin token as bearer and accepts empty delete responses', async () => {
		const { fn, calls } = fakeFetch(204);
		const res = await createApi(BASE, fn).admin.deleteProblem('s3cret', 7n);
		expect(res.ok).toBe(true);
		expect(calls[0]).toMatchObject({
			url: 'http://api:8000/api/v1/admin/problems/7',
			method: 'DELETE',
			headers: { Authorization: 'Bearer s3cret' }
		});
	});

	it('verifies the admin token by status code only', async () => {
		const ok = fakeFetch(200, { admin: true });
		expect((await createApi(BASE, ok.fn).admin.verify('t')).ok).toBe(true);
		const denied = fakeFetch(401, { error: 'unauthorized' });
		expect(await createApi(BASE, denied.fn).admin.verify('bad')).toEqual({
			ok: false,
			status: 401,
			error: 'unauthorized'
		});
	});

	it('creates problems with nested test cases', async () => {
		const { fn, calls } = fakeFetch(200, {
			problem: { ...problemJson, statement: 's', samples: [] }
		});
		const res = await createApi(BASE, fn).admin.createProblem('t', {
			slug: 'a-plus-b',
			title: 'A + B',
			statement: 's',
			difficulty: Difficulty.MEDIUM,
			timeLimitMs: 1000,
			memoryLimitMb: 128,
			testCases: [{ input: '1 2', expectedOutput: '3', isSample: true }]
		});
		expect(res.ok && res.data.id).toBe(7n);
		expect(calls[0].body).toEqual({
			slug: 'a-plus-b',
			title: 'A + B',
			statement: 's',
			difficulty: 'DIFFICULTY_MEDIUM',
			timeLimitMs: 1000,
			memoryLimitMb: 128,
			testCases: [{ input: '1 2', expectedOutput: '3', isSample: true }]
		});
	});

	it('adds a test case with the problem id in the path only', async () => {
		const { fn, calls } = fakeFetch(200, {
			testCase: { id: '3', problemId: '7', input: '', expectedOutput: '0', ordinal: 3 }
		});
		const res = await createApi(BASE, fn).admin.addTestCase('t', 7n, {
			input: '',
			expectedOutput: '0',
			isSample: false
		});
		expect(res.ok && res.data.ordinal).toBe(3);
		expect(calls[0].url).toBe('http://api:8000/api/v1/admin/problems/7/testcases');
		expect(calls[0].body).toEqual({ testCase: { expectedOutput: '0' } });
	});

	it('lists and deletes test cases', async () => {
		const { fn, calls } = fakeFetch(200, { testCases: [{ id: '3', ordinal: 1, isSample: true }] });
		const api = createApi(BASE, fn);
		const list = await api.admin.testCases('t', 7n);
		expect(list.ok && list.data[0].isSample).toBe(true);
		await api.admin.deleteTestCase('t', 7n, 3n);
		expect(calls[1]).toMatchObject({
			url: 'http://api:8000/api/v1/admin/problems/7/testcases/3',
			method: 'DELETE'
		});
	});

	it('uses a per-call fetch when given (SvelteKit event.fetch)', async () => {
		const unused = fakeFetch(500);
		const used = fakeFetch(200, { healthy: true, runners: 2, queueDepth: '4' });
		const res = await createApi(BASE, unused.fn).status(used.fn);
		expect(unused.calls).toHaveLength(0);
		expect(res.ok && res.data.queueDepth).toBe(4n);
	});
});

describe('helpers', () => {
	it('parseId accepts positive int64 ids only', () => {
		expect(parseId('42')).toBe(42n);
		expect(parseId('9223372036854775807')).toBe(9223372036854775807n);
		for (const bad of ['0', '-1', '1.5', 'abc', '', null, '01', '9223372036854775808']) {
			expect(parseId(bad)).toBeNull();
		}
	});

	it('toQuery drops proto defaults and empty values', () => {
		expect(toQuery({ a: 1, b: '', c: 0, d: 0n, e: null, f: undefined, g: 'x y' })).toBe(
			'?a=1&g=x+y'
		);
		expect(toQuery({})).toBe('');
	});
});

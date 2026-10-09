import { describe, expect, it } from 'vitest';
import { createApi, formatDetail, toQuery } from './client.js';

type Call = { url: string; init: RequestInit };

function fakeFetch(status: number, body?: unknown, headers: Record<string, string> = {}) {
	const calls: Call[] = [];
	const fn = (async (url: string, init: RequestInit) => {
		calls.push({ url, init });
		return new Response(body === undefined ? null : JSON.stringify(body), { status, headers });
	}) as unknown as typeof fetch;
	return { fn, calls };
}

const api = createApi('http://rest/api/v1');

const problem = {
	id: 1,
	slug: 'a-plus-b',
	title: 'A + B',
	difficulty: 'easy',
	time_limit_ms: 1000,
	memory_limit_mb: 128
};

describe('toQuery', () => {
	it('drops empty values and encodes the rest', () => {
		expect(toQuery({ a: 1, b: '', c: null, d: 'x y' })).toBe('?a=1&d=x+y');
		expect(toQuery({})).toBe('');
	});
});

describe('formatDetail', () => {
	it('flattens FastAPI validation errors', () => {
		expect(
			formatDetail([
				{ loc: ['body', 'username'], msg: 'bad' },
				{ loc: ['body'], msg: 'worse' }
			])
		).toBe('username: bad; worse');
		expect(formatDetail('plain')).toBe('plain');
		expect(formatDetail(undefined)).toBe('');
	});
});

describe('createApi', () => {
	it('returns data that matches the contract', async () => {
		const { fn, calls } = fakeFetch(200, [problem]);
		const res = await api.problems(fn);
		expect(res).toEqual({ ok: true, data: [problem] });
		expect(calls[0].url).toBe('http://rest/api/v1/problems');
	});

	it('rejects responses that break the contract', async () => {
		const { fn } = fakeFetch(200, [{ id: 'one' }]);
		expect(await api.problems(fn)).toEqual({
			ok: false,
			status: 502,
			error: 'API response did not match the contract'
		});
	});

	it('sends JSON, the admin token and the client IP', async () => {
		const { fn, calls } = fakeFetch(200, {
			status: 'OK',
			compile_output: '',
			stdout: '3\n',
			stderr: '',
			exit_code: 0,
			time_ms: 5,
			memory_kb: 100
		});
		await api.run(fn, { language: 'python', source: 'print(3)', stdin: '' }, '1.2.3.4');
		const headers = calls[0].init.headers as Record<string, string>;
		expect(calls[0].init.method).toBe('POST');
		expect(JSON.parse(String(calls[0].init.body))).toMatchObject({ language: 'python' });
		expect(headers['X-Real-IP']).toBe('1.2.3.4');

		const admin = fakeFetch(204);
		await api.admin.deleteProblem(admin.fn, 'tok', 5);
		expect((admin.calls[0].init.headers as Record<string, string>).Authorization).toBe(
			'Bearer tok'
		);
	});

	it('maps error payloads to readable messages', async () => {
		expect(await api.problem(fakeFetch(404, { detail: 'not found' }).fn, 9)).toEqual({
			ok: false,
			status: 404,
			error: 'not found'
		});
		const limited = await api.submit(
			fakeFetch(429, { detail: 'x' }, { 'Retry-After': '3' }).fn,
			{ problem_id: 1, language: 'python', source: 'x', username: 'me' }
		);
		expect(limited).toMatchObject({ ok: false, status: 429, error: 'Too many requests. Try again in 3s.' });
	});

	it('reports an unreachable backend as 503', async () => {
		const failing = (async () => {
			throw new TypeError('connection refused');
		}) as unknown as typeof fetch;
		expect(await api.languages(failing)).toMatchObject({ ok: false, status: 503 });
	});
});

/**
 * In-memory stand-in for the api (/api/v1, canonical proto JSON) so the e2e specs can run
 * without the backend. Judging is faked: a submission is PENDING, then JUDGING, then
 * FINISHED; it is Accepted when the source computes `a + b` (or `sum(`), else Wrong Answer.
 *
 *   node e2e/mock-api.ts            # PORT (default 8099), ADMIN_TOKEN (default e2e-admin-token)
 *
 * The JSON here is written by hand on purpose: it double-checks that the webapp parses
 * what the contract says goes over the wire (camelCase, enum names, int64 as strings).
 */
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';

const PORT = Number(process.env.PORT ?? 8099);
const ADMIN_TOKEN = process.env.ADMIN_TOKEN ?? 'e2e-admin-token';

interface TestCase {
	id: number;
	input: string;
	expectedOutput: string;
	isSample: boolean;
}
interface Problem {
	id: number;
	slug: string;
	title: string;
	statement: string;
	difficulty: string;
	timeLimitMs: number;
	memoryLimitMb: number;
	tests: TestCase[];
}
interface Submission {
	id: number;
	problemId: number;
	username: string;
	language: string;
	source: string;
	accepted: boolean;
	created: number;
}

let nextId = 100;
const problems: Problem[] = [
	{
		id: 1,
		slug: 'a-plus-b',
		title: 'A + B',
		statement:
			'Read two integers **A** and **B** separated by whitespace and print their sum.\n\n### Input\nA single line containing two integers `A` and `B`.\n\n### Output\nPrint `A + B`.',
		difficulty: 'DIFFICULTY_EASY',
		timeLimitMs: 1000,
		memoryLimitMb: 128,
		tests: [
			{ id: 1, input: '1 2', expectedOutput: '3', isSample: true },
			{ id: 2, input: '-5 5', expectedOutput: '0', isSample: true },
			{ id: 3, input: '1000000000 1000000000', expectedOutput: '2000000000', isSample: false }
		]
	}
];
const submissions: Submission[] = [];

const summary = (p: Problem) => ({
	id: String(p.id),
	slug: p.slug,
	title: p.title,
	difficulty: p.difficulty,
	timeLimitMs: p.timeLimitMs,
	memoryLimitMb: p.memoryLimitMb
});
const detail = (p: Problem) => ({
	...summary(p),
	statement: p.statement,
	samples: p.tests
		.filter((t) => t.isSample)
		.map((t) => ({ input: t.input, output: t.expectedOutput }))
});
const testCase = (p: Problem, t: TestCase, i: number) => ({
	id: String(t.id),
	problemId: String(p.id),
	input: t.input,
	expectedOutput: t.expectedOutput,
	isSample: t.isSample,
	ordinal: i + 1
});

function submissionJson(s: Submission, full: boolean) {
	const age = Date.now() - s.created;
	const problem = problems.find((p) => p.id === s.problemId);
	const total = problem?.tests.length ?? 0;
	const base = {
		id: String(s.id),
		problemId: String(s.problemId),
		username: s.username,
		language: s.language,
		createTime: new Date(s.created).toISOString(),
		updateTime: new Date(s.created + Math.min(age, 1500)).toISOString()
	};
	if (age < 500)
		return { ...base, status: 'SUBMISSION_STATUS_PENDING', ...(full && { source: s.source }) };
	if (age < 1500)
		return { ...base, status: 'SUBMISSION_STATUS_JUDGING', ...(full && { source: s.source }) };
	const failing = s.accepted ? -1 : 0;
	const results = Array.from({ length: total }, (_, i) => ({
		test: i + 1,
		verdict: i === failing ? 'VERDICT_WRONG_ANSWER' : 'VERDICT_ACCEPTED',
		timeMs: 10 + i,
		memoryKb: '9216',
		sample: problem?.tests[i]?.isSample ?? false
	}));
	return {
		...base,
		status: 'SUBMISSION_STATUS_FINISHED',
		verdict: s.accepted ? 'VERDICT_ACCEPTED' : 'VERDICT_WRONG_ANSWER',
		passed: s.accepted ? total : 0,
		total,
		timeMs: 10 + total,
		...(full && {
			source: s.source,
			message: s.accepted ? '' : 'Wrong Answer on test 1',
			results
		})
	};
}

const solves = (source: string) => /a\s*\+\s*b|sum\(/.test(source);

function send(
	res: ServerResponse,
	status: number,
	body?: unknown,
	headers: Record<string, string> = {}
) {
	res.writeHead(status, { 'Content-Type': 'application/json', ...headers });
	res.end(body === undefined ? '' : JSON.stringify(body));
}
const fail = (res: ServerResponse, status: number, error: string, details: string[] = []) =>
	send(res, status, { error, details });

async function readJson(req: IncomingMessage): Promise<Record<string, unknown>> {
	let raw = '';
	for await (const chunk of req) raw += chunk;
	return raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
}

async function handle(req: IncomingMessage, res: ServerResponse): Promise<void> {
	const url = new URL(req.url ?? '/', 'http://mock');
	const path = url.pathname.replace(/^\/api\/v1/, '');
	const method = req.method ?? 'GET';
	const seg = path.split('/').filter(Boolean);

	if (seg[0] === 'admin') {
		if (req.headers.authorization !== `Bearer ${ADMIN_TOKEN}`)
			return fail(res, 401, 'unauthorized');
		if (path === '/admin/verify') return send(res, 200, { admin: true });
		if (path === '/admin/problems' && method === 'POST') {
			const b = await readJson(req);
			if (problems.some((p) => p.slug === b.slug)) return fail(res, 409, 'slug already exists');
			const tcs = (b.testCases as Record<string, unknown>[] | undefined) ?? [];
			const p: Problem = {
				id: nextId++,
				slug: String(b.slug),
				title: String(b.title),
				statement: String(b.statement ?? ''),
				difficulty: String(b.difficulty ?? 'DIFFICULTY_EASY'),
				timeLimitMs: Number(b.timeLimitMs ?? 2000),
				memoryLimitMb: Number(b.memoryLimitMb ?? 256),
				tests: tcs.map((t) => ({
					id: nextId++,
					input: String(t.input ?? ''),
					expectedOutput: String(t.expectedOutput ?? ''),
					isSample: Boolean(t.isSample)
				}))
			};
			problems.push(p);
			return send(res, 200, { problem: detail(p) });
		}
		const p = problems.find((x) => String(x.id) === seg[2]);
		if (!p) return fail(res, 404, 'problem not found');
		if (seg.length === 3 && method === 'DELETE') {
			problems.splice(problems.indexOf(p), 1);
			return send(res, 200, {});
		}
		if (seg[3] === 'testcases' && seg.length === 4 && method === 'GET') {
			return send(res, 200, { testCases: p.tests.map((t, i) => testCase(p, t, i)) });
		}
		if (seg[3] === 'testcases' && seg.length === 4 && method === 'POST') {
			const t = ((await readJson(req)).testCase ?? {}) as Record<string, unknown>;
			const tc = {
				id: nextId++,
				input: String(t.input ?? ''),
				expectedOutput: String(t.expectedOutput ?? ''),
				isSample: Boolean(t.isSample)
			};
			p.tests.push(tc);
			return send(res, 200, { testCase: testCase(p, tc, p.tests.length - 1) });
		}
		if (seg[3] === 'testcases' && seg.length === 5 && method === 'DELETE') {
			const i = p.tests.findIndex((t) => String(t.id) === seg[4]);
			if (i < 0) return fail(res, 404, 'test case not found');
			p.tests.splice(i, 1);
			return send(res, 204);
		}
		return fail(res, 404, 'not found');
	}

	if (path === '/status') {
		return send(res, 200, {
			healthy: true,
			database: 'ok',
			broker: 'ok',
			queueDepth: '0',
			runners: 1
		});
	}
	if (path === '/languages') {
		return send(res, 200, {
			languages: [
				{ language: 'LANGUAGE_PYTHON', name: 'Python 3' },
				{ language: 'LANGUAGE_C', name: 'C (gcc)' },
				{ language: 'LANGUAGE_CPP', name: 'C++17 (g++)' },
				{ language: 'LANGUAGE_JAVASCRIPT', name: 'JavaScript (Node.js)' }
			]
		});
	}
	if (path === '/problems') return send(res, 200, { problems: problems.map(summary) });
	if (seg[0] === 'problems' && seg.length === 2) {
		const p = problems.find((x) => String(x.id) === seg[1]);
		return p ? send(res, 200, { problem: detail(p) }) : fail(res, 404, 'problem not found');
	}
	if (path === '/submissions' && method === 'POST') {
		const b = await readJson(req);
		if (!problems.some((p) => String(p.id) === b.problemId))
			return fail(res, 404, 'problem not found');
		if (!String(b.source ?? '').trim())
			return fail(res, 422, 'invalid argument', ['source: empty']);
		const s: Submission = {
			id: nextId++,
			problemId: Number(b.problemId),
			username: String(b.username ?? ''),
			language: String(b.language),
			source: String(b.source),
			accepted: solves(String(b.source)),
			created: Date.now()
		};
		submissions.unshift(s);
		return send(res, 200, { submission: submissionJson(s, true) });
	}
	if (path === '/submissions') {
		const pid = url.searchParams.get('problemId');
		const user = url.searchParams.get('username');
		const limit = Number(url.searchParams.get('limit') || 50);
		const offset = Number(url.searchParams.get('offset') || 0);
		const list = submissions
			.filter((s) => (!pid || String(s.problemId) === pid) && (!user || s.username === user))
			.slice(offset, offset + limit)
			.map((s) => submissionJson(s, false));
		return send(res, 200, { submissions: list });
	}
	if (seg[0] === 'submissions' && seg.length === 2) {
		const s = submissions.find((x) => String(x.id) === seg[1]);
		return s
			? send(res, 200, { submission: submissionJson(s, true) })
			: fail(res, 404, 'not found');
	}
	if (path === '/run' && method === 'POST') {
		const b = await readJson(req);
		const nums = String(b.stdin ?? '')
			.split(/\s+/)
			.filter(Boolean)
			.map(Number);
		const stdout = solves(String(b.source ?? '')) ? `${nums.reduce((a, n) => a + n, 0)}\n` : '';
		return send(res, 200, {
			status: 'RUN_STATUS_OK',
			stdout,
			timeMs: 12,
			memoryKb: '9216'
		});
	}
	return fail(res, 404, 'not found');
}

createServer((req, res) => {
	handle(req, res).catch((err: unknown) => fail(res, 500, String(err)));
}).listen(PORT, '127.0.0.1', () => console.log(`mock api on http://127.0.0.1:${PORT}/api/v1`));

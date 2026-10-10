import { error } from '@sveltejs/kit';
import {
	create,
	fromJson,
	toJson,
	type DescMessage,
	type MessageInitShape,
	type MessageShape
} from '@bufbuild/protobuf';
import { API_URL } from '$app/env/private';
import {
	AddProblemRequestSchema,
	AddProblemResponseSchema,
	AddTestCaseRequestSchema,
	AddTestCaseResponseSchema,
	GetProblemDetailResponseSchema,
	GetStatusResponseSchema,
	GetSubmissionDetailResponseSchema,
	ListLanguagesResponseSchema,
	ListProblemSummariesResponseSchema,
	ListProblemTestCasesResponseSchema,
	ListSubmissionSummariesResponseSchema,
	RemoveProblemResponseSchema,
	RemoveTestCaseResponseSchema,
	RunCodeRequestSchema,
	RunCodeResponseSchema,
	SubmitRequestSchema,
	SubmitResponseSchema,
	type NewTestCase
} from '#lib/gen/oj/v1/judge_pb.js';
import { ErrorResponseSchema } from '#lib/gen/oj/v1/types_pb.js';
import { query } from '#lib/url.js';

/**
 * Repository for the oj-rest public API (/api/v1). Bodies are canonical proto JSON:
 * requests are built with `create()` + `toJson()`, every response is validated with
 * `fromJson()` against the shared schema, and errors are `ErrorResponse`.
 */

export type ApiResult<T> = { ok: true; data: T } | { ok: false; status: number; error: string };

export interface RequestOptions {
	method?: string;
	/** Canonical proto JSON body. */
	body?: unknown;
	/** Admin bearer token. */
	token?: string | null;
	/** Visitor IP, forwarded so oj-rest rate-limits per visitor rather than per webapp. */
	clientIp?: string;
}

export type Id = bigint | number;

export interface SubmissionQuery {
	problemId?: Id;
	username?: string;
	limit?: number;
	offset?: number;
}

export const CONTRACT_ERROR = 'API response did not match the contract';

/** Query string of the set params (`?a=1&b=x`, or '' when none). */
export function toQuery(params: Record<string, string | number | bigint | null | undefined>) {
	// Zero is the proto default ("not set"), so it is left out like empty values.
	return query(Object.fromEntries(Object.entries(params).filter(([, v]) => v !== 0 && v !== 0n)));
}

function errorMessage(status: number, json: unknown, retryAfter: string | null): string {
	if (status === 429) {
		return `Too many requests. Try again ${retryAfter ? `in ${retryAfter}s` : 'shortly'}.`;
	}
	try {
		const err = fromJson(ErrorResponseSchema, json as never, { ignoreUnknownFields: true });
		const details = err.details.filter(Boolean).join('; ');
		if (err.error) return details ? `${err.error}: ${details}` : err.error;
	} catch {
		// Not an ErrorResponse (e.g. a proxy's HTML error page); fall through.
	}
	return `Request failed (HTTP ${status})`;
}

export function createApi(baseUrl: string, fetchImpl: typeof fetch = fetch) {
	const base = baseUrl.replace(/\/+$/, '');

	async function request<Desc extends DescMessage>(
		path: string,
		schema: Desc | null,
		opts: RequestOptions = {},
		fetchFn: typeof fetch = fetchImpl
	): Promise<ApiResult<MessageShape<Desc>>> {
		const headers: Record<string, string> = { Accept: 'application/json' };
		if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
		if (opts.token) headers.Authorization = `Bearer ${opts.token}`;
		if (opts.clientIp) headers['X-Real-IP'] = opts.clientIp;

		let res: Response;
		try {
			res = await fetchFn(`${base}${path}`, {
				method: opts.method ?? 'GET',
				headers,
				body: opts.body === undefined ? undefined : JSON.stringify(opts.body)
			});
		} catch {
			return { ok: false, status: 503, error: 'The judge is unreachable' };
		}

		const text = await res.text().catch(() => '');
		let json: unknown = {};
		let parsed = true;
		if (text.trim()) {
			try {
				json = JSON.parse(text);
			} catch {
				parsed = false;
			}
		}

		if (!res.ok) {
			return {
				ok: false,
				status: res.status,
				error: errorMessage(res.status, json, res.headers.get('Retry-After'))
			};
		}
		if (!parsed) return { ok: false, status: 502, error: CONTRACT_ERROR };
		// `null` schema: any 2xx is success (routes outside the proto contract, e.g. /admin/verify).
		if (schema === null) return { ok: true, data: undefined as unknown as MessageShape<Desc> };
		try {
			return {
				ok: true,
				data: fromJson(schema, json as never, { ignoreUnknownFields: true })
			};
		} catch {
			return { ok: false, status: 502, error: CONTRACT_ERROR };
		}
	}

	/** Unwrap a required sub-message: absent means the response broke the contract. */
	function field<T, U>(res: ApiResult<T>, pick: (t: T) => U | undefined): ApiResult<U> {
		if (!res.ok) return res;
		const value = pick(res.data);
		return value === undefined
			? { ok: false, status: 502, error: CONTRACT_ERROR }
			: { ok: true, data: value };
	}

	return {
		status: async (f?: typeof fetch) => request('/status', GetStatusResponseSchema, {}, f),

		languages: async (f?: typeof fetch) =>
			field(await request('/languages', ListLanguagesResponseSchema, {}, f), (r) => r.languages),

		problems: async (f?: typeof fetch) =>
			field(
				await request('/problems', ListProblemSummariesResponseSchema, {}, f),
				(r) => r.problems
			),

		problem: async (id: Id, f?: typeof fetch) =>
			field(
				await request(`/problems/${id}`, GetProblemDetailResponseSchema, {}, f),
				(r) => r.problem
			),

		submissions: async (q: SubmissionQuery = {}, f?: typeof fetch) =>
			field(
				await request(
					`/submissions${toQuery({ ...q })}`,
					ListSubmissionSummariesResponseSchema,
					{},
					f
				),
				(r) => r.submissions
			),

		submission: async (id: Id, f?: typeof fetch) =>
			field(
				await request(`/submissions/${id}`, GetSubmissionDetailResponseSchema, {}, f),
				(r) => r.submission
			),

		submit: async (
			init: MessageInitShape<typeof SubmitRequestSchema>,
			clientIp?: string,
			f?: typeof fetch
		) => {
			const body = toJson(SubmitRequestSchema, create(SubmitRequestSchema, init));
			return field(
				await request('/submissions', SubmitResponseSchema, { method: 'POST', body, clientIp }, f),
				(r) => r.submission
			);
		},

		run: async (
			init: MessageInitShape<typeof RunCodeRequestSchema>,
			clientIp?: string,
			f?: typeof fetch
		) => {
			const body = toJson(RunCodeRequestSchema, create(RunCodeRequestSchema, init));
			return request('/run', RunCodeResponseSchema, { method: 'POST', body, clientIp }, f);
		},

		admin: {
			/** 2xx when the token is valid (oj-rest-only route, not part of the proto contract). */
			verify: async (token: string, f?: typeof fetch) =>
				request('/admin/verify', null, { token }, f),

			createProblem: async (
				token: string,
				init: MessageInitShape<typeof AddProblemRequestSchema>,
				f?: typeof fetch
			) => {
				const body = toJson(AddProblemRequestSchema, create(AddProblemRequestSchema, init));
				return field(
					await request(
						'/admin/problems',
						AddProblemResponseSchema,
						{ method: 'POST', body, token },
						f
					),
					(r) => r.problem
				);
			},

			deleteProblem: async (token: string, id: Id, f?: typeof fetch) =>
				request(
					`/admin/problems/${id}`,
					RemoveProblemResponseSchema,
					{ method: 'DELETE', token },
					f
				),

			testCases: async (token: string, problemId: Id, f?: typeof fetch) =>
				field(
					await request(
						`/admin/problems/${problemId}/testcases`,
						ListProblemTestCasesResponseSchema,
						{ token },
						f
					),
					(r) => r.testCases
				),

			addTestCase: async (
				token: string,
				problemId: Id,
				testCase: MessageInitShape<typeof AddTestCaseRequestSchema>['testCase'],
				f?: typeof fetch
			) => {
				// problemId travels in the path; the body is the rest of AddTestCaseRequest.
				const body = toJson(
					AddTestCaseRequestSchema,
					create(AddTestCaseRequestSchema, { testCase })
				);
				return field(
					await request(
						`/admin/problems/${problemId}/testcases`,
						AddTestCaseResponseSchema,
						{ method: 'POST', body, token },
						f
					),
					(r) => r.testCase
				);
			},

			deleteTestCase: async (token: string, problemId: Id, id: Id, f?: typeof fetch) =>
				request(
					`/admin/problems/${problemId}/testcases/${id}`,
					RemoveTestCaseResponseSchema,
					{ method: 'DELETE', token },
					f
				)
		}
	};
}

export type Api = ReturnType<typeof createApi>;
export type { NewTestCase };

/** The oj-rest repository, bound to the configured API_URL. */
export const api = createApi(API_URL);

/** Positive integer id from a route param or form field, else null. */
export function parseId(raw: unknown): bigint | null {
	const s = String(raw ?? '').trim();
	if (!/^[1-9]\d{0,18}$/.test(s)) return null;
	const id = BigInt(s);
	return id <= 9223372036854775807n ? id : null;
}

/** For load functions: the data, or throw the API error as an HTTP error page. */
export function unwrap<T>(res: ApiResult<T>): T {
	if (res.ok) return res.data;
	error(res.status >= 400 && res.status <= 599 ? res.status : 502, res.error);
}

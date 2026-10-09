import {
	anything,
	arrayOf,
	isLanguage,
	isProblemDetail,
	isProblemSummary,
	isRunResult,
	isServiceStatus,
	isSubmissionDetail,
	isSubmissionSummary,
	type Guard,
	type NewProblem
} from '#lib/types.js';

/** Repository for the oj-rest public API. Every response is checked against its contract. */

export type ApiResult<T> = { ok: true; data: T } | { ok: false; status: number; error: string };

export interface RequestInit {
	method?: string;
	body?: unknown;
	/** Admin bearer token. */
	token?: string | null;
	/** End user's IP, forwarded so oj-rest rate-limits per visitor rather than per webapp. */
	clientIp?: string;
}

/** Turn FastAPI / gateway error payloads into one readable string. */
export function formatDetail(detail: unknown): string {
	if (!detail) return '';
	if (typeof detail === 'string') return detail;
	if (Array.isArray(detail)) {
		return detail
			.map((d: { loc?: unknown[]; msg?: string }) => {
				const loc = (d.loc ?? []).filter((p) => p !== 'body').join('.');
				return loc ? `${loc}: ${d.msg}` : (d.msg ?? '');
			})
			.join('; ');
	}
	return JSON.stringify(detail);
}

export function toQuery(params: Record<string, string | number | null | undefined>): string {
	const q = new URLSearchParams();
	for (const [k, v] of Object.entries(params)) {
		if (v !== undefined && v !== null && v !== '') q.set(k, String(v));
	}
	const s = q.toString();
	return s ? `?${s}` : '';
}

export function createApi(baseUrl: string) {
	async function request<T>(
		fetchFn: typeof fetch,
		path: string,
		guard: Guard<T>,
		init: RequestInit = {}
	): Promise<ApiResult<T>> {
		const headers: Record<string, string> = { Accept: 'application/json' };
		if (init.body !== undefined) headers['Content-Type'] = 'application/json';
		if (init.token) headers.Authorization = `Bearer ${init.token}`;
		if (init.clientIp) headers['X-Real-IP'] = init.clientIp;

		let res: Response;
		try {
			res = await fetchFn(`${baseUrl}${path}`, {
				method: init.method ?? 'GET',
				headers,
				body: init.body === undefined ? undefined : JSON.stringify(init.body)
			});
		} catch {
			return { ok: false, status: 503, error: 'The judge is unreachable' };
		}

		if (res.status === 204) return guard(null) ? { ok: true, data: null as T } : contractError();
		const json: unknown = await res.json().catch(() => ({}));
		if (!res.ok) {
			const detail = formatDetail((json as { detail?: unknown }).detail);
			let error = detail || 'Request failed';
			if (res.status === 429) {
				const retry = res.headers.get('Retry-After');
				error = `Too many requests. Try again${retry ? ` in ${retry}s` : ' shortly'}.`;
			}
			return { ok: false, status: res.status, error };
		}
		return guard(json) ? { ok: true, data: json } : contractError();
	}

	function contractError(): ApiResult<never> {
		return { ok: false, status: 502, error: 'API response did not match the contract' };
	}

	type SubmissionQuery = { problem_id?: number | null; username?: string | null; limit?: number };

	return {
		status: (f: typeof fetch) => request(f, '/status', isServiceStatus),
		languages: (f: typeof fetch) => request(f, '/languages', arrayOf(isLanguage)),
		problems: (f: typeof fetch) => request(f, '/problems', arrayOf(isProblemSummary)),
		problem: (f: typeof fetch, id: number) => request(f, `/problems/${id}`, isProblemDetail),
		submissions: (f: typeof fetch, q: SubmissionQuery = {}) =>
			request(f, `/submissions${toQuery(q)}`, arrayOf(isSubmissionSummary)),
		submission: (f: typeof fetch, id: number) =>
			request(f, `/submissions/${id}`, isSubmissionDetail),
		submit: (
			f: typeof fetch,
			body: { problem_id: number; language: string; source: string; username: string },
			clientIp?: string
		) => request(f, '/submissions', isSubmissionDetail, { method: 'POST', body, clientIp }),
		run: (
			f: typeof fetch,
			body: { language: string; source: string; stdin: string; problem_id?: number },
			clientIp?: string
		) => request(f, '/run', isRunResult, { method: 'POST', body, clientIp }),
		admin: {
			verify: (f: typeof fetch, token: string) =>
				request(f, '/admin/verify', anything, { token }),
			createProblem: (f: typeof fetch, token: string, body: NewProblem) =>
				request(f, '/admin/problems', isProblemDetail, { method: 'POST', body, token }),
			deleteProblem: (f: typeof fetch, token: string, id: number) =>
				request(f, `/admin/problems/${id}`, anything, { method: 'DELETE', token })
		}
	};
}

export type Api = ReturnType<typeof createApi>;

import { error, fail } from '@sveltejs/kit';
import { parseTestCases, validateTestCase } from '#lib/admin-form.js';
import { requireAdmin } from '#lib/server/admin.js';
import { api, parseId, unwrap } from '#lib/server/api.js';
import type { Actions, PageServerLoad } from './$types';

function problemId(raw: string): bigint {
	const id = parseId(raw);
	if (id === null) error(404, 'Problem not found');
	return id;
}

export const load: PageServerLoad = async ({ params, fetch, locals, url, parent }) => {
	await parent();
	const token = requireAdmin(locals, url);
	const id = problemId(params.id);
	const [problem, testCases] = await Promise.all([
		api.problem(id, fetch),
		api.admin.testCases(token, id, fetch)
	]);
	return { problem: unwrap(problem), testCases: unwrap(testCases) };
};

export const actions: Actions = {
	add: async ({ request, params, locals, url, fetch }) => {
		const token = requireAdmin(locals, url);
		const id = problemId(params.id);
		const [tc] = parseTestCases(await request.formData());
		const message = tc ? validateTestCase(tc) : 'Missing test case.';
		if (message || !tc) return fail(400, { error: message });

		const res = await api.admin.addTestCase(token, id, tc, fetch);
		if (!res.ok) return fail(res.status, { error: res.error });
		return { added: res.data.ordinal };
	},

	delete: async ({ request, params, locals, url, fetch }) => {
		const token = requireAdmin(locals, url);
		const id = problemId(params.id);
		const tcId = parseId((await request.formData()).get('id'));
		if (tcId === null) return fail(400, { error: 'Invalid test case id.' });

		const res = await api.admin.deleteTestCase(token, id, tcId, fetch);
		if (!res.ok) return fail(res.status, { error: res.error });
		return { deleted: String(tcId) };
	}
};

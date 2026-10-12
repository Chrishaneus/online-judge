import { fail } from '@sveltejs/kit';
import { requireAdmin } from '#lib/server/admin.js';
import { api, parseId, unwrap } from '#lib/server/api.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, parent }) => {
	await parent();
	return { problems: unwrap(await api.problems(fetch)) };
};

export const actions: Actions = {
	delete: async ({ request, locals, url, fetch }) => {
		const token = requireAdmin(locals, url);
		const form = await request.formData();
		const id = parseId(form.get('id'));
		const title = String(form.get('title') ?? `#${id}`);
		if (id === null) return fail(400, { error: 'Invalid problem id.' });

		const res = await api.admin.deleteProblem(token, id, fetch);
		if (!res.ok) return fail(res.status, { error: res.error });
		return { deleted: title };
	}
};

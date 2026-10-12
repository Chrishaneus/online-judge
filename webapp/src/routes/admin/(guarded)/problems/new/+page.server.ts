import { fail, redirect } from '@sveltejs/kit';
import { parseProblemForm } from '#lib/admin-form.js';
import { requireAdmin } from '#lib/server/admin.js';
import { api } from '#lib/server/api.js';
import type { Actions } from './$types';

export const actions: Actions = {
	default: async ({ request, locals, url, fetch }) => {
		const token = requireAdmin(locals, url);
		const { problem, errors } = parseProblemForm(await request.formData());
		if (Object.keys(errors).length) return fail(400, { errors, error: null });

		const res = await api.admin.createProblem(token, problem, fetch);
		if (!res.ok) return fail(res.status, { errors, error: res.error });
		redirect(303, `/admin/problems/${res.data.id}?created=1`);
	}
};

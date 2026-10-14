import { fail, redirect } from '@sveltejs/kit';
import { safeAdminRedirect, setAdminCookie } from '#lib/server/admin.js';
import { api } from '#lib/server/api.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = ({ locals, url }) => {
	if (locals.adminToken) redirect(303, safeAdminRedirect(url.searchParams.get('redirectTo')));
};

export const actions: Actions = {
	default: async ({ request, cookies, url, fetch, locals }) => {
		const token = String((await request.formData()).get('token') ?? '').trim();
		if (!token) return fail(400, { error: 'Enter the admin token.' });

		const res = await api.admin.verify(token, fetch);
		if (!res.ok) {
			const error = res.status === 401 || res.status === 403 ? 'Invalid admin token.' : res.error;
			return fail(res.status === 401 || res.status === 403 ? 401 : res.status, { error });
		}
		setAdminCookie(cookies, url, token);
		locals.adminToken = token;
		redirect(303, safeAdminRedirect(url.searchParams.get('redirectTo')));
	}
};

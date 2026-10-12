import { redirect } from '@sveltejs/kit';
import { clearAdminCookie } from '#lib/server/admin.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = () => redirect(303, '/admin');

export const actions: Actions = {
	default: ({ cookies, locals }) => {
		clearAdminCookie(cookies);
		locals.adminToken = null;
		redirect(303, '/admin/login');
	}
};

import type { Handle } from '@sveltejs/kit/hooks';
import { ADMIN_COOKIE, clearAdminCookie } from '#lib/server/admin.js';
import { api } from '#lib/server/api.js';

export const handle: Handle = async ({ event, resolve }) => {
	event.locals.adminToken = null;

	// The admin token is only needed (and only verified) on admin pages and their actions.
	const token = event.cookies.get(ADMIN_COOKIE);
	if (token && event.url.pathname.startsWith('/admin')) {
		const res = await api.admin.verify(token, event.fetch);
		if (res.ok) event.locals.adminToken = token;
		else if (res.status === 401 || res.status === 403) clearAdminCookie(event.cookies);
	}

	return resolve(event);
};

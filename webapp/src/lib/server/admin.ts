import { redirect, type Cookies } from '@sveltejs/kit';

/** httpOnly cookie holding the admin bearer token (verified against the api on every admin request). */
export const ADMIN_COOKIE = 'oj_admin';

export function setAdminCookie(cookies: Cookies, url: URL, token: string): void {
	cookies.set(ADMIN_COOKIE, token, {
		path: '/',
		httpOnly: true,
		sameSite: 'strict',
		secure: url.protocol === 'https:',
		maxAge: 60 * 60 * 8
	});
}

export function clearAdminCookie(cookies: Cookies): void {
	cookies.delete(ADMIN_COOKIE, { path: '/' });
}

/** Token of the verified admin, or redirect to the login page. Form actions must call this too. */
export function requireAdmin(locals: App.Locals, url: URL): string {
	if (!locals.adminToken) {
		redirect(303, `/admin/login?redirectTo=${encodeURIComponent(url.pathname + url.search)}`);
	}
	return locals.adminToken;
}

/** Only allow same-site relative paths under /admin, to prevent open redirects after login. */
export function safeAdminRedirect(target: string | null): string {
	if (!target || !target.startsWith('/admin') || target.startsWith('/admin/login')) return '/admin';
	return target;
}

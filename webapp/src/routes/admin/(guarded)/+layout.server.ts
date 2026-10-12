import { requireAdmin } from '#lib/server/admin.js';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = ({ locals, url }) => {
	requireAdmin(locals, url);
	return {};
};

import { api, unwrap } from '#lib/server/api.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => ({
	problems: unwrap(await api.problems(fetch))
});

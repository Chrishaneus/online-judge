import { error } from '@sveltejs/kit';
import { api, parseId, unwrap } from '#lib/server/api.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params, fetch, depends }) => {
	depends('app:submission');
	const id = parseId(params.id);
	if (id === null) error(404, 'Submission not found');
	const [submission, languages] = await Promise.all([
		api.submission(id, fetch),
		api.languages(fetch)
	]);
	return { submission: unwrap(submission), languages: languages.ok ? languages.data : [] };
};

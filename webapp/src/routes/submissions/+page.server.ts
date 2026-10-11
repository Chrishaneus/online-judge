import { sanitizeUsername } from '#lib/drafts.js';
import { api, parseId, unwrap } from '#lib/server/api.js';
import type { PageServerLoad } from './$types';

const PAGE_SIZE = 25;

export const load: PageServerLoad = async ({ url, fetch, depends }) => {
	depends('app:submissions');
	const username = sanitizeUsername(url.searchParams.get('user') ?? '');
	const problemId = parseId(url.searchParams.get('problem')) ?? 0n;
	const pageRaw = Number(url.searchParams.get('page'));
	const page = Number.isSafeInteger(pageRaw) && pageRaw > 1 ? pageRaw : 1;

	// Ask for one extra row to know whether a next page exists.
	const [subs, languages] = await Promise.all([
		api.submissions(
			{ username, problemId, limit: PAGE_SIZE + 1, offset: (page - 1) * PAGE_SIZE },
			fetch
		),
		api.languages(fetch)
	]);
	const rows = unwrap(subs);
	return {
		submissions: rows.slice(0, PAGE_SIZE),
		hasNext: rows.length > PAGE_SIZE,
		page,
		filter: { username, problemId: problemId ? String(problemId) : null },
		languages: languages.ok ? languages.data : []
	};
};

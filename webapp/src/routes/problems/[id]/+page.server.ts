import { error, fail, redirect } from '@sveltejs/kit';
import { parseLanguage } from '#lib/labels.js';
import { sanitizeUsername } from '#lib/drafts.js';
import { api, parseId, unwrap } from '#lib/server/api.js';
import type { Actions, PageServerLoad } from './$types';

const MAX_SOURCE = 262_144;
const MAX_STDIN = 1 << 20;

function problemId(raw: string): bigint {
	const id = parseId(raw);
	if (id === null) error(404, 'Problem not found');
	return id;
}

export const load: PageServerLoad = async ({ params, fetch }) => {
	const id = problemId(params.id);
	const [problem, languages] = await Promise.all([api.problem(id, fetch), api.languages(fetch)]);
	return { problem: unwrap(problem), languages: unwrap(languages) };
};

/** Shared validation of the editor form. */
async function readEditor(request: Request) {
	const form = await request.formData();
	const language = parseLanguage(form.get('language'));
	const source = String(form.get('source') ?? '');
	const stdin = String(form.get('stdin') ?? '');
	const username = sanitizeUsername(String(form.get('username') ?? ''));
	let message: string | null = null;
	if (language === null) message = 'Choose a language.';
	else if (!source.trim()) message = 'Write some code first.';
	else if (source.length > MAX_SOURCE) message = 'Source code is too long (max 256 KiB).';
	else if (stdin.length > MAX_STDIN) message = 'Input is too long (max 1 MiB).';
	return { language: language ?? 0, source, stdin, username, message };
}

export const actions: Actions = {
	run: async ({ request, params, fetch, getClientAddress }) => {
		const id = problemId(params.id);
		const f = await readEditor(request);
		if (f.message) return fail(400, { action: 'run' as const, error: f.message });

		const res = await api.run(
			{ language: f.language, source: f.source, stdin: f.stdin, problemId: id },
			getClientAddress(),
			fetch
		);
		if (!res.ok) return fail(res.status, { action: 'run' as const, error: res.error });
		return { action: 'run' as const, run: res.data };
	},

	submit: async ({ request, params, fetch, getClientAddress }) => {
		const id = problemId(params.id);
		const f = await readEditor(request);
		if (f.message) return fail(400, { action: 'submit' as const, error: f.message });

		const res = await api.submit(
			{ problemId: id, language: f.language, source: f.source, username: f.username },
			getClientAddress(),
			fetch
		);
		if (!res.ok) return fail(res.status, { action: 'submit' as const, error: res.error });
		redirect(303, `/submissions/${res.data.id}`);
	}
};

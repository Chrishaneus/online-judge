import { Language } from '#lib/gen/oj/v1/types_pb.js';

/** Starter code and browser-side persistence for the problem editor (drafts, username, language). */

export const TEMPLATES: Partial<Record<Language, string>> = {
	[Language.PYTHON]:
		'import sys\n\n\ndef main():\n    data = sys.stdin.read().split()\n    \n\n\nmain()\n',
	[Language.CPP]:
		'#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n    \n    return 0;\n}\n',
	[Language.C]: '#include <stdio.h>\n\nint main(void) {\n    \n    return 0;\n}\n',
	[Language.JAVASCRIPT]:
		"const input = require('fs').readFileSync(0, 'utf8');\nconst lines = input.trim().split('\\n');\n\n"
};

export function template(lang: Language): string {
	return TEMPLATES[lang] ?? '';
}

/** The subset of `Storage` we use; localStorage in the browser, a fake in tests. */
export type KeyValueStore = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

const PREFIX = 'oj.';
export const USERNAME_KEY = `${PREFIX}username`;
export const LANGUAGE_KEY = `${PREFIX}language`;

export function draftKey(problemId: bigint | number, lang: Language): string {
	return `${PREFIX}draft.${problemId}.${Language[lang] ?? lang}`;
}

/** localStorage, or null when unavailable (SSR, privacy mode, blocked storage). */
export function browserStore(): KeyValueStore | null {
	try {
		return typeof localStorage === 'undefined' ? null : localStorage;
	} catch {
		return null;
	}
}

function get(store: KeyValueStore | null, key: string): string | null {
	try {
		return store?.getItem(key) ?? null;
	} catch {
		return null;
	}
}

function set(store: KeyValueStore | null, key: string, value: string): void {
	try {
		store?.setItem(key, value);
	} catch {
		// Quota exceeded or storage blocked: drafts are a convenience, never fail on them.
	}
}

/** Saved draft for this problem and language, else the language's starter template. */
export function loadDraft(
	store: KeyValueStore | null,
	problemId: bigint | number,
	lang: Language
): string {
	return get(store, draftKey(problemId, lang)) ?? template(lang);
}

/** Save a draft; an unchanged template is not worth keeping. */
export function saveDraft(
	store: KeyValueStore | null,
	problemId: bigint | number,
	lang: Language,
	source: string
): void {
	const key = draftKey(problemId, lang);
	if (source === template(lang)) {
		try {
			store?.removeItem(key);
		} catch {
			// ignore
		}
	} else {
		set(store, key, source);
	}
}

/** Usernames rest accepts: [A-Za-z0-9_.-]{0,32} (empty means anonymous). */
export function sanitizeUsername(value: string): string {
	return value.replace(/[^A-Za-z0-9_.-]/g, '').slice(0, 32);
}

export function loadUsername(store: KeyValueStore | null): string {
	return sanitizeUsername(get(store, USERNAME_KEY) ?? '');
}

export function saveUsername(store: KeyValueStore | null, username: string): void {
	set(store, USERNAME_KEY, sanitizeUsername(username));
}

/** Last used language if it is still offered, else the first available one. */
export function loadLanguage(
	store: KeyValueStore | null,
	available: readonly Language[]
): Language {
	const saved = Language[(get(store, LANGUAGE_KEY) ?? '') as keyof typeof Language];
	if (saved !== undefined && available.includes(saved)) return saved;
	return available[0] ?? Language.PYTHON;
}

export function saveLanguage(store: KeyValueStore | null, lang: Language): void {
	set(store, LANGUAGE_KEY, Language[lang]);
}

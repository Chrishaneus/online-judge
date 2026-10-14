import { describe, expect, it } from 'vitest';
import { Language } from '#lib/gen/oj/v1/types_pb.js';
import {
	draftKey,
	loadDraft,
	loadLanguage,
	loadUsername,
	sanitizeUsername,
	saveDraft,
	saveLanguage,
	saveUsername,
	template,
	type KeyValueStore
} from './drafts.js';

function memoryStore(): KeyValueStore & { data: Map<string, string> } {
	const data = new Map<string, string>();
	return {
		data,
		getItem: (k) => data.get(k) ?? null,
		setItem: (k, v) => void data.set(k, v),
		removeItem: (k) => void data.delete(k)
	};
}

const brokenStore: KeyValueStore = {
	getItem: () => {
		throw new Error('SecurityError');
	},
	setItem: () => {
		throw new Error('QuotaExceededError');
	},
	removeItem: () => {
		throw new Error('SecurityError');
	}
};

describe('drafts', () => {
	it('starts from the language template', () => {
		const store = memoryStore();
		expect(loadDraft(store, 1n, Language.PYTHON)).toBe(template(Language.PYTHON));
		expect(template(Language.CPP)).toContain('int main()');
		expect(template(Language.C)).toContain('#include <stdio.h>');
		expect(template(Language.JAVASCRIPT)).toContain("require('fs')");
		expect(template(Language.UNSPECIFIED)).toBe('');
	});

	it('keeps one draft per problem and language', () => {
		const store = memoryStore();
		saveDraft(store, 1n, Language.PYTHON, 'print(1)');
		saveDraft(store, 1n, Language.CPP, '// cpp');
		saveDraft(store, 2n, Language.PYTHON, 'print(2)');

		expect(loadDraft(store, 1n, Language.PYTHON)).toBe('print(1)');
		expect(loadDraft(store, 1n, Language.CPP)).toBe('// cpp');
		expect(loadDraft(store, 2n, Language.PYTHON)).toBe('print(2)');
		expect(loadDraft(store, 2n, Language.CPP)).toBe(template(Language.CPP));
		expect(draftKey(1n, Language.PYTHON)).toBe('oj.draft.1.PYTHON');
	});

	it('drops a draft that equals the template', () => {
		const store = memoryStore();
		saveDraft(store, 1n, Language.PYTHON, 'x');
		saveDraft(store, 1n, Language.PYTHON, template(Language.PYTHON));
		expect(store.data.size).toBe(0);
	});

	it('never throws when storage is unavailable', () => {
		expect(loadDraft(null, 1n, Language.C)).toBe(template(Language.C));
		expect(loadDraft(brokenStore, 1n, Language.C)).toBe(template(Language.C));
		expect(() => saveDraft(brokenStore, 1n, Language.C, 'x')).not.toThrow();
		expect(() => saveDraft(brokenStore, 1n, Language.C, template(Language.C))).not.toThrow();
		expect(() => saveUsername(brokenStore, 'a')).not.toThrow();
		expect(loadUsername(brokenStore)).toBe('');
	});
});

describe('username and language', () => {
	it('sanitizes usernames to what oj-rest accepts', () => {
		expect(sanitizeUsername('al ice<script>!')).toBe('alicescript');
		expect(sanitizeUsername('a.b-c_d9')).toBe('a.b-c_d9');
		expect(sanitizeUsername('x'.repeat(40))).toHaveLength(32);
	});

	it('remembers the username', () => {
		const store = memoryStore();
		expect(loadUsername(store)).toBe('');
		saveUsername(store, 'bob smith');
		expect(loadUsername(store)).toBe('bobsmith');
	});

	it('remembers the language while it is still offered', () => {
		const store = memoryStore();
		const offered = [Language.PYTHON, Language.CPP];
		expect(loadLanguage(store, offered)).toBe(Language.PYTHON);
		saveLanguage(store, Language.CPP);
		expect(loadLanguage(store, offered)).toBe(Language.CPP);
		expect(loadLanguage(store, [Language.C])).toBe(Language.C);
		store.setItem('oj.language', 'COBOL');
		expect(loadLanguage(store, offered)).toBe(Language.PYTHON);
	});
});

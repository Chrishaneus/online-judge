import { describe, expect, it } from 'vitest';
import { Difficulty } from '#lib/gen/oj/v1/types_pb.js';
import { parseProblemForm, parseTestCases } from './admin-form.js';

function formData(entries: [string, string][]): FormData {
	const f = new FormData();
	for (const [k, v] of entries) f.append(k, v);
	return f;
}

const valid: [string, string][] = [
	['slug', 'a-plus-b'],
	['title', 'A + B'],
	['statement', 'Add them.'],
	['difficulty', '2'],
	['timeLimitMs', '1000'],
	['memoryLimitMb', '128'],
	['tcInput', '1 2'],
	['tcExpected', '3'],
	['tcSample', '0'],
	['tcInput', '5 5'],
	['tcExpected', '10']
];

describe('admin problem form', () => {
	it('parses a valid form, matching sample checkboxes to their rows', () => {
		const { problem, errors } = parseProblemForm(formData(valid));
		expect(errors).toEqual({});
		expect(problem).toEqual({
			slug: 'a-plus-b',
			title: 'A + B',
			statement: 'Add them.',
			difficulty: Difficulty.MEDIUM,
			timeLimitMs: 1000,
			memoryLimitMb: 128,
			testCases: [
				{ input: '1 2', expectedOutput: '3', isSample: true },
				{ input: '5 5', expectedOutput: '10', isSample: false }
			]
		});
	});

	it('only the checked rows are samples', () => {
		const tcs = parseTestCases(
			formData([
				['tcInput', 'a'],
				['tcExpected', 'A'],
				['tcInput', 'b'],
				['tcExpected', 'B'],
				['tcSample', '1']
			])
		);
		expect(tcs.map((t) => t.isSample)).toEqual([false, true]);
	});

	it('reports every invalid field', () => {
		const { errors } = parseProblemForm(
			formData([
				['slug', 'Not A Slug'],
				['title', ''],
				['statement', ' '],
				['timeLimitMs', '50'],
				['memoryLimitMb', '4096']
			])
		);
		expect(Object.keys(errors).sort()).toEqual([
			'memoryLimitMb',
			'slug',
			'statement',
			'testCases',
			'timeLimitMs',
			'title'
		]);
	});

	it('requires an expected output for every test case', () => {
		const { errors } = parseProblemForm(
			formData([
				...valid.filter(([k]) => !k.startsWith('tc')),
				['tcInput', '1'],
				['tcExpected', '']
			])
		);
		expect(errors.testCases).toMatch(/expected output/);
	});

	it('defaults missing limits and difficulty like the API', () => {
		const { problem } = parseProblemForm(
			formData(valid.filter(([k]) => !['timeLimitMs', 'memoryLimitMb', 'difficulty'].includes(k)))
		);
		expect(problem).toMatchObject({
			timeLimitMs: 2000,
			memoryLimitMb: 256,
			difficulty: Difficulty.EASY
		});
	});
});

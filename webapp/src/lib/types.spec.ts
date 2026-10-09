import { describe, expect, it } from 'vitest';
import { arrayOf, isProblemDetail, isSubmissionDetail, isSubmissionSummary } from './types.js';

const summary = {
	id: 1,
	problem_id: 2,
	username: 'u',
	language: 'python',
	status: 'FINISHED',
	verdict: 'AC',
	passed: 3,
	total: 3,
	time_ms: 10,
	created_at: '2026-01-01T00:00:00Z'
};

describe('guards', () => {
	it('accepts valid shapes and ignores extra fields', () => {
		expect(isSubmissionSummary({ ...summary, extra: true })).toBe(true);
		expect(
			isSubmissionDetail({
				...summary,
				source: 'x',
				message: '',
				results: [],
				updated_at: summary.created_at
			})
		).toBe(true);
	});

	it('rejects missing or mistyped fields', () => {
		expect(isSubmissionSummary({ ...summary, id: '1' })).toBe(false);
		expect(isSubmissionDetail(summary)).toBe(false);
		expect(isSubmissionSummary(null)).toBe(false);
		expect(isSubmissionSummary([summary])).toBe(false);
	});

	it('validates nested samples', () => {
		const problem = {
			id: 1,
			slug: 's',
			title: 't',
			difficulty: 'easy',
			time_limit_ms: 1,
			memory_limit_mb: 1,
			statement: '',
			samples: [{ input: '1', output: '2' }]
		};
		expect(isProblemDetail(problem)).toBe(true);
		expect(isProblemDetail({ ...problem, samples: [{ input: 1 }] })).toBe(false);
	});

	it('arrayOf checks every element', () => {
		expect(arrayOf(isSubmissionSummary)([summary, summary])).toBe(true);
		expect(arrayOf(isSubmissionSummary)([summary, {}])).toBe(false);
		expect(arrayOf(isSubmissionSummary)({})).toBe(false);
	});
});

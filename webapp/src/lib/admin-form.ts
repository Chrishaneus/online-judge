import { Difficulty } from '#lib/gen/oj/v1/types_pb.js';
import { parseDifficulty } from '#lib/labels.js';

/** Parsing and validation of the admin problem / test case forms (mirrors midlayer's rules). */

export const SLUG_PATTERN = '[a-z0-9]+(-[a-z0-9]+)*';
const SLUG_RE = new RegExp(`^${SLUG_PATTERN}$`);
const MAX_TEST_DATA = 8 << 20;

export interface TestCaseInput {
	input: string;
	expectedOutput: string;
	isSample: boolean;
}

export interface ProblemInput {
	slug: string;
	title: string;
	statement: string;
	difficulty: Difficulty;
	timeLimitMs: number;
	memoryLimitMb: number;
	testCases: TestCaseInput[];
}

export type FormErrors = Partial<Record<keyof ProblemInput, string>>;

function int(value: FormDataEntryValue | null, fallback: number): number {
	const s = String(value ?? '').trim();
	return s === '' ? fallback : Number(s);
}

/**
 * Test case rows come as parallel `tcInput` / `tcExpected` lists; a sample checkbox
 * posts its row index as `tcSample` (unchecked boxes post nothing).
 */
export function parseTestCases(form: FormData): TestCaseInput[] {
	const inputs = form.getAll('tcInput').map(String);
	const expected = form.getAll('tcExpected').map(String);
	const samples = new Set(form.getAll('tcSample').map(String));
	return inputs.map((input, i) => ({
		input,
		expectedOutput: expected[i] ?? '',
		isSample: samples.has(String(i))
	}));
}

export function validateTestCase(tc: TestCaseInput): string | null {
	if (!tc.expectedOutput.trim()) return 'Every test case needs an expected output.';
	if (tc.input.length > MAX_TEST_DATA || tc.expectedOutput.length > MAX_TEST_DATA) {
		return 'Test data is limited to 8 MiB per input / output.';
	}
	return null;
}

export function parseProblemForm(form: FormData): { problem: ProblemInput; errors: FormErrors } {
	const problem: ProblemInput = {
		slug: String(form.get('slug') ?? '').trim(),
		title: String(form.get('title') ?? '').trim(),
		statement: String(form.get('statement') ?? ''),
		difficulty: parseDifficulty(form.get('difficulty')) ?? Difficulty.EASY,
		timeLimitMs: int(form.get('timeLimitMs'), 2000),
		memoryLimitMb: int(form.get('memoryLimitMb'), 256),
		testCases: parseTestCases(form)
	};

	const errors: FormErrors = {};
	if (!problem.slug) errors.slug = 'Slug is required.';
	else if (problem.slug.length > 64 || !SLUG_RE.test(problem.slug)) {
		errors.slug = 'Lowercase letters, digits and single dashes (max 64), e.g. two-sum.';
	}
	if (!problem.title) errors.title = 'Title is required.';
	else if (problem.title.length > 200) errors.title = 'Title is at most 200 characters.';
	if (!problem.statement.trim()) errors.statement = 'Statement is required.';
	if (
		!Number.isInteger(problem.timeLimitMs) ||
		problem.timeLimitMs < 100 ||
		problem.timeLimitMs > 15000
	) {
		errors.timeLimitMs = 'Between 100 and 15000 ms.';
	}
	if (
		!Number.isInteger(problem.memoryLimitMb) ||
		problem.memoryLimitMb < 16 ||
		problem.memoryLimitMb > 1024
	) {
		errors.memoryLimitMb = 'Between 16 and 1024 MB.';
	}
	if (problem.testCases.length === 0) errors.testCases = 'Add at least one test case.';
	else if (problem.testCases.length > 200) errors.testCases = 'At most 200 test cases.';
	else {
		const tcError = problem.testCases.map(validateTestCase).find(Boolean);
		if (tcError) errors.testCases = tcError;
	}
	return { problem, errors };
}

/**
 * Shapes of the oj-rest public API, with runtime guards. Every response is
 * checked against its guard in the API repository, so a contract drift shows
 * up as a clear 502 instead of `undefined` deep inside a component.
 */

export type Difficulty = 'easy' | 'medium' | 'hard';
export type SubmissionStatus = 'PENDING' | 'JUDGING' | 'FINISHED' | 'FAILED';
export type Verdict = 'AC' | 'WA' | 'TLE' | 'MLE' | 'OLE' | 'RE' | 'CE' | 'IE' | '';
export type RunStatus = 'OK' | 'TLE' | 'MLE' | 'OLE' | 'RE' | 'CE';

export interface Language {
	id: string;
	name: string;
}

export interface ProblemSummary {
	id: number;
	slug: string;
	title: string;
	difficulty: Difficulty;
	time_limit_ms: number;
	memory_limit_mb: number;
}

export interface Sample {
	input: string;
	output: string;
}

export interface ProblemDetail extends ProblemSummary {
	statement: string;
	samples: Sample[];
}

export interface TestResult {
	test: number;
	verdict: Verdict;
	time_ms: number;
	memory_kb: number;
	sample: boolean;
}

export interface SubmissionSummary {
	id: number;
	problem_id: number;
	username: string;
	language: string;
	status: SubmissionStatus;
	verdict: Verdict;
	passed: number;
	total: number;
	time_ms: number;
	created_at: string;
}

export interface SubmissionDetail extends SubmissionSummary {
	source: string;
	message: string;
	results: TestResult[];
	updated_at: string;
}

export interface RunResult {
	status: RunStatus;
	compile_output: string;
	stdout: string;
	stderr: string;
	exit_code: number;
	time_ms: number;
	memory_kb: number;
}

export interface ServiceStatus {
	status: string;
	dao: string;
	runner: string;
	queue_depth: number;
}

export interface NewTestCase {
	input: string;
	expected_output: string;
	is_sample: boolean;
}

export interface NewProblem {
	slug: string;
	title: string;
	statement: string;
	difficulty: Difficulty;
	time_limit_ms: number;
	memory_limit_mb: number;
	test_cases: NewTestCase[];
}

// ---------- guards ----------

export type Guard<T> = (value: unknown) => value is T;

type FieldType = 'string' | 'number' | 'boolean' | 'array' | 'object';

function hasFields(value: unknown, fields: Record<string, FieldType>): value is Record<string, unknown> {
	if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
	const obj = value as Record<string, unknown>;
	return Object.entries(fields).every(([key, type]) => {
		const v = obj[key];
		if (type === 'array') return Array.isArray(v);
		if (type === 'object') return typeof v === 'object' && v !== null && !Array.isArray(v);
		return typeof v === type;
	});
}

export function arrayOf<T>(guard: Guard<T>): Guard<T[]> {
	return (value: unknown): value is T[] => Array.isArray(value) && value.every(guard);
}

export const anything: Guard<unknown> = (_value: unknown): _value is unknown => true;

export const isLanguage: Guard<Language> = (v): v is Language =>
	hasFields(v, { id: 'string', name: 'string' });

export const isProblemSummary: Guard<ProblemSummary> = (v): v is ProblemSummary =>
	hasFields(v, {
		id: 'number',
		slug: 'string',
		title: 'string',
		difficulty: 'string',
		time_limit_ms: 'number',
		memory_limit_mb: 'number'
	});

const isSample: Guard<Sample> = (v): v is Sample => hasFields(v, { input: 'string', output: 'string' });

export const isProblemDetail: Guard<ProblemDetail> = (v): v is ProblemDetail =>
	isProblemSummary(v) &&
	hasFields(v, { statement: 'string', samples: 'array' }) &&
	(v as unknown as ProblemDetail).samples.every(isSample);

export const isSubmissionSummary: Guard<SubmissionSummary> = (v): v is SubmissionSummary =>
	hasFields(v, {
		id: 'number',
		problem_id: 'number',
		username: 'string',
		language: 'string',
		status: 'string',
		verdict: 'string',
		passed: 'number',
		total: 'number',
		time_ms: 'number',
		created_at: 'string'
	});

export const isSubmissionDetail: Guard<SubmissionDetail> = (v): v is SubmissionDetail =>
	isSubmissionSummary(v) &&
	hasFields(v, { source: 'string', message: 'string', results: 'array', updated_at: 'string' });

export const isRunResult: Guard<RunResult> = (v): v is RunResult =>
	hasFields(v, {
		status: 'string',
		compile_output: 'string',
		stdout: 'string',
		stderr: 'string',
		exit_code: 'number',
		time_ms: 'number',
		memory_kb: 'number'
	});

export const isServiceStatus: Guard<ServiceStatus> = (v): v is ServiceStatus =>
	hasFields(v, { status: 'string', dao: 'string', runner: 'string' });

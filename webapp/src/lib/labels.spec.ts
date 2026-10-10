import { describe, expect, it } from 'vitest';
import { create } from '@bufbuild/protobuf';
import { LanguageInfoSchema } from '#lib/gen/oj/v1/judge_pb.js';
import {
	Difficulty,
	Language,
	RunStatus,
	SubmissionStatus,
	Verdict
} from '#lib/gen/oj/v1/types_pb.js';
import {
	difficultyLabel,
	formatMemoryKb,
	isFinal,
	languageKey,
	languageName,
	parseDifficulty,
	parseLanguage,
	runStatusLabel,
	statusLabel,
	submissionLabel,
	timeAgo,
	verdictLabel
} from './labels.js';

describe('verdicts', () => {
	it('has a human label, short code and tone for every verdict', () => {
		expect(verdictLabel(Verdict.ACCEPTED)).toEqual({
			label: 'Accepted',
			short: 'AC',
			tone: 'success'
		});
		expect(verdictLabel(Verdict.WRONG_ANSWER)).toMatchObject({
			label: 'Wrong Answer',
			tone: 'danger'
		});
		expect(verdictLabel(Verdict.TIME_LIMIT_EXCEEDED).label).toBe('Time Limit Exceeded');
		expect(verdictLabel(Verdict.MEMORY_LIMIT_EXCEEDED).short).toBe('MLE');
		expect(verdictLabel(Verdict.OUTPUT_LIMIT_EXCEEDED).short).toBe('OLE');
		expect(verdictLabel(Verdict.RUNTIME_ERROR).label).toBe('Runtime Error');
		expect(verdictLabel(Verdict.COMPILATION_ERROR).label).toBe('Compilation Error');
		expect(verdictLabel(Verdict.INTERNAL_ERROR).label).toBe('Internal Error');
		const all = Object.values(Verdict).filter((v): v is Verdict => typeof v === 'number');
		for (const v of all) expect(verdictLabel(v).label).toBeTruthy();
	});

	it('falls back for values from a newer contract', () => {
		expect(verdictLabel(99 as Verdict).label).toBe('Not judged');
		expect(statusLabel(99 as SubmissionStatus).label).toBe('Unknown');
		expect(runStatusLabel(99 as RunStatus).label).toBe('Unknown');
		expect(difficultyLabel(99 as Difficulty).label).toBe('Unrated');
	});

	it('shows the status until a submission is finished, then the verdict', () => {
		expect(
			submissionLabel({ status: SubmissionStatus.PENDING, verdict: Verdict.UNSPECIFIED }).label
		).toBe('Pending');
		expect(
			submissionLabel({ status: SubmissionStatus.JUDGING, verdict: Verdict.UNSPECIFIED }).label
		).toBe('Judging');
		expect(
			submissionLabel({ status: SubmissionStatus.FINISHED, verdict: Verdict.ACCEPTED }).label
		).toBe('Accepted');
		expect(
			submissionLabel({ status: SubmissionStatus.FAILED, verdict: Verdict.UNSPECIFIED })
		).toMatchObject({ label: 'Judging failed', tone: 'danger' });
	});

	it('knows which statuses are final', () => {
		expect(isFinal(SubmissionStatus.FINISHED)).toBe(true);
		expect(isFinal(SubmissionStatus.FAILED)).toBe(true);
		expect(isFinal(SubmissionStatus.PENDING)).toBe(false);
		expect(isFinal(SubmissionStatus.JUDGING)).toBe(false);
		expect(isFinal(SubmissionStatus.UNSPECIFIED)).toBe(false);
	});

	it('labels run statuses', () => {
		expect(runStatusLabel(RunStatus.OK)).toMatchObject({ label: 'OK', tone: 'success' });
		expect(runStatusLabel(RunStatus.COMPILATION_ERROR).label).toBe('Compilation Error');
	});
});

describe('difficulty', () => {
	it('labels and parses difficulties', () => {
		expect(difficultyLabel(Difficulty.EASY)).toMatchObject({ label: 'Easy', tone: 'success' });
		expect(difficultyLabel(Difficulty.MEDIUM)).toMatchObject({ label: 'Medium', tone: 'warning' });
		expect(difficultyLabel(Difficulty.HARD)).toMatchObject({ label: 'Hard', tone: 'danger' });
		expect(parseDifficulty('2')).toBe(Difficulty.MEDIUM);
		expect(parseDifficulty('0')).toBeNull();
		expect(parseDifficulty('x')).toBeNull();
	});
});

describe('languages', () => {
	const langs = [
		create(LanguageInfoSchema, { language: Language.PYTHON, name: 'Python 3.13' }),
		create(LanguageInfoSchema, { language: Language.CPP, name: 'C++17 (g++)' })
	];

	it('uses the ListLanguages name, then a built-in fallback', () => {
		expect(languageName(langs, Language.PYTHON)).toBe('Python 3.13');
		expect(languageName(langs, Language.CPP)).toBe('C++17 (g++)');
		expect(languageName(langs, Language.JAVASCRIPT)).toBe('JavaScript');
		expect(languageName([], Language.C)).toBe('C');
		expect(languageName([], Language.UNSPECIFIED)).toBe('Unknown');
	});

	it('parses form values into specified languages only', () => {
		expect(parseLanguage('1')).toBe(Language.PYTHON);
		expect(parseLanguage('CPP')).toBe(Language.CPP);
		expect(parseLanguage('LANGUAGE_JAVASCRIPT')).toBe(Language.JAVASCRIPT);
		expect(parseLanguage('python')).toBe(Language.PYTHON);
		for (const bad of ['0', 'UNSPECIFIED', '', null, '99', 'ruby', 'toString']) {
			expect(parseLanguage(bad)).toBeNull();
		}
	});

	it('has stable lowercase keys', () => {
		expect(languageKey(Language.CPP)).toBe('cpp');
		expect(languageKey(99 as Language)).toBe('unknown');
	});
});

describe('formatting', () => {
	it('formats memory', () => {
		expect(formatMemoryKb(512)).toBe('512 KB');
		expect(formatMemoryKb(2048n)).toBe('2.0 MB');
		expect(formatMemoryKb(262144)).toBe('256 MB');
	});

	it('formats relative times', () => {
		const now = new Date('2026-11-05T12:00:00Z');
		expect(timeAgo(new Date('2026-11-05T11:59:30Z'), now)).toBe('30s ago');
		expect(timeAgo(new Date('2026-11-05T11:55:00Z'), now)).toBe('5 min ago');
		expect(timeAgo(new Date('2026-11-05T09:00:00Z'), now)).toBe('3 h ago');
		expect(timeAgo(new Date('2026-11-03T12:00:00Z'), now)).toBe('2 d ago');
		expect(timeAgo(new Date('2026-10-01T12:00:00Z'), now)).toBe('2026-10-01');
		expect(timeAgo(undefined, now)).toBe('');
	});
});

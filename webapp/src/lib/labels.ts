import type { LanguageInfo } from '#lib/gen/oj/v1/judge_pb.js';
import {
	Difficulty,
	Language,
	RunStatus,
	SubmissionStatus,
	Verdict
} from '#lib/gen/oj/v1/types_pb.js';

/** Display helpers for the proto enums. Colours are Tailwind classes that work in light and dark mode. */

export type Tone = 'success' | 'danger' | 'warning' | 'info' | 'neutral' | 'purple';

export const TONE_CLASSES: Record<Tone, string> = {
	success: 'bg-green-600/10 text-green-700 dark:bg-green-400/15 dark:text-green-400',
	danger: 'bg-red-600/10 text-red-700 dark:bg-red-400/15 dark:text-red-400',
	warning: 'bg-amber-500/15 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300',
	info: 'bg-blue-600/10 text-blue-700 dark:bg-blue-400/15 dark:text-blue-300',
	purple: 'bg-purple-600/10 text-purple-700 dark:bg-purple-400/15 dark:text-purple-300',
	neutral: 'bg-muted text-muted-foreground'
};

export interface Label {
	label: string;
	/** Short code shown in compact places (AC, WA, …). */
	short: string;
	tone: Tone;
}

// ---------- languages ----------

/** Stable lowercase key of a language (`python`, `cpp`), used for drafts and templates. */
export function languageKey(lang: Language): string {
	return Language[lang]?.toLowerCase() ?? 'unknown';
}

/** Parse a form value (enum number, `PYTHON` or `LANGUAGE_PYTHON`) into a known, specified language. */
export function parseLanguage(value: unknown): Language | null {
	const raw = String(value ?? '')
		.trim()
		.toUpperCase()
		.replace(/^LANGUAGE_/, '');
	if (!raw) return null;
	const n: unknown = /^\d+$/.test(raw)
		? Number(raw)
		: (Language as unknown as Record<string, unknown>)[raw];
	return typeof n === 'number' && n !== Language.UNSPECIFIED && Language[n] !== undefined
		? (n as Language)
		: null;
}

const FALLBACK_LANGUAGE_NAMES: Partial<Record<Language, string>> = {
	[Language.PYTHON]: 'Python 3',
	[Language.C]: 'C',
	[Language.CPP]: 'C++',
	[Language.JAVASCRIPT]: 'JavaScript'
};

/** Display name from ListLanguages, falling back to a built-in name. */
export function languageName(languages: readonly LanguageInfo[], lang: Language): string {
	return (
		languages.find((l) => l.language === lang)?.name ||
		FALLBACK_LANGUAGE_NAMES[lang] ||
		(lang === Language.UNSPECIFIED ? 'Unknown' : languageKey(lang))
	);
}

// ---------- difficulty ----------

const DIFFICULTY: Record<Difficulty, Label> = {
	[Difficulty.UNSPECIFIED]: { label: 'Unrated', short: '?', tone: 'neutral' },
	[Difficulty.EASY]: { label: 'Easy', short: 'easy', tone: 'success' },
	[Difficulty.MEDIUM]: { label: 'Medium', short: 'medium', tone: 'warning' },
	[Difficulty.HARD]: { label: 'Hard', short: 'hard', tone: 'danger' }
};

export function difficultyLabel(d: Difficulty): Label {
	return DIFFICULTY[d] ?? DIFFICULTY[Difficulty.UNSPECIFIED];
}

export const DIFFICULTY_OPTIONS = [Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD] as const;

export function parseDifficulty(value: unknown): Difficulty | null {
	const n = Number(value);
	return DIFFICULTY_OPTIONS.includes(n as (typeof DIFFICULTY_OPTIONS)[number])
		? (n as Difficulty)
		: null;
}

// ---------- verdicts and statuses ----------

const VERDICT: Record<Verdict, Label> = {
	[Verdict.UNSPECIFIED]: { label: 'Not judged', short: '–', tone: 'neutral' },
	[Verdict.ACCEPTED]: { label: 'Accepted', short: 'AC', tone: 'success' },
	[Verdict.WRONG_ANSWER]: { label: 'Wrong Answer', short: 'WA', tone: 'danger' },
	[Verdict.TIME_LIMIT_EXCEEDED]: { label: 'Time Limit Exceeded', short: 'TLE', tone: 'warning' },
	[Verdict.MEMORY_LIMIT_EXCEEDED]: {
		label: 'Memory Limit Exceeded',
		short: 'MLE',
		tone: 'warning'
	},
	[Verdict.OUTPUT_LIMIT_EXCEEDED]: {
		label: 'Output Limit Exceeded',
		short: 'OLE',
		tone: 'warning'
	},
	[Verdict.RUNTIME_ERROR]: { label: 'Runtime Error', short: 'RE', tone: 'purple' },
	[Verdict.COMPILATION_ERROR]: { label: 'Compilation Error', short: 'CE', tone: 'info' },
	[Verdict.INTERNAL_ERROR]: { label: 'Internal Error', short: 'IE', tone: 'neutral' }
};

export function verdictLabel(v: Verdict): Label {
	return VERDICT[v] ?? VERDICT[Verdict.UNSPECIFIED];
}

const STATUS: Record<SubmissionStatus, Label> = {
	[SubmissionStatus.UNSPECIFIED]: { label: 'Unknown', short: '?', tone: 'neutral' },
	[SubmissionStatus.PENDING]: { label: 'Pending', short: 'Pending', tone: 'neutral' },
	[SubmissionStatus.JUDGING]: { label: 'Judging', short: 'Judging', tone: 'info' },
	[SubmissionStatus.FINISHED]: { label: 'Finished', short: 'Finished', tone: 'neutral' },
	[SubmissionStatus.FAILED]: { label: 'Judging failed', short: 'Failed', tone: 'danger' }
};

export function statusLabel(s: SubmissionStatus): Label {
	return STATUS[s] ?? STATUS[SubmissionStatus.UNSPECIFIED];
}

/** FINISHED and FAILED never change again; anything else is still being judged. */
export function isFinal(status: SubmissionStatus): boolean {
	return status === SubmissionStatus.FINISHED || status === SubmissionStatus.FAILED;
}

/** What to show for a submission: the verdict once finished, else its status. */
export function submissionLabel(sub: { status: SubmissionStatus; verdict: Verdict }): Label {
	if (sub.status === SubmissionStatus.FINISHED && sub.verdict !== Verdict.UNSPECIFIED) {
		return verdictLabel(sub.verdict);
	}
	return statusLabel(sub.status);
}

const RUN_STATUS: Record<RunStatus, Label> = {
	[RunStatus.UNSPECIFIED]: { label: 'Unknown', short: '?', tone: 'neutral' },
	[RunStatus.OK]: { label: 'OK', short: 'OK', tone: 'success' },
	[RunStatus.TIME_LIMIT_EXCEEDED]: { label: 'Time Limit Exceeded', short: 'TLE', tone: 'warning' },
	[RunStatus.MEMORY_LIMIT_EXCEEDED]: {
		label: 'Memory Limit Exceeded',
		short: 'MLE',
		tone: 'warning'
	},
	[RunStatus.OUTPUT_LIMIT_EXCEEDED]: {
		label: 'Output Limit Exceeded',
		short: 'OLE',
		tone: 'warning'
	},
	[RunStatus.RUNTIME_ERROR]: { label: 'Runtime Error', short: 'RE', tone: 'purple' },
	[RunStatus.COMPILATION_ERROR]: { label: 'Compilation Error', short: 'CE', tone: 'info' }
};

export function runStatusLabel(s: RunStatus): Label {
	return RUN_STATUS[s] ?? RUN_STATUS[RunStatus.UNSPECIFIED];
}

// ---------- formatting ----------

export function formatMemoryKb(kbValue: number | bigint): string {
	const kb = Number(kbValue);
	if (kb < 1024) return `${kb} KB`;
	const mb = kb / 1024;
	return `${mb < 10 ? mb.toFixed(1) : Math.round(mb)} MB`;
}

/** "5s ago", "3 min ago", "2 h ago", or a date for anything older than a week. */
export function timeAgo(date: Date | undefined, now: Date = new Date()): string {
	if (!date) return '';
	const s = Math.max(0, Math.round((now.getTime() - date.getTime()) / 1000));
	if (s < 60) return `${s}s ago`;
	if (s < 3600) return `${Math.floor(s / 60)} min ago`;
	if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
	if (s < 7 * 86400) return `${Math.floor(s / 86400)} d ago`;
	return date.toISOString().slice(0, 10);
}

import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { SubmissionStatus, Verdict } from '#lib/gen/oj/v1/types_pb.js';
import VerdictBadge from './verdict-badge.svelte';

describe('verdict-badge.svelte', () => {
	it('shows the human verdict once finished', async () => {
		render(VerdictBadge, { status: SubmissionStatus.FINISHED, verdict: Verdict.ACCEPTED });
		const badge = page.getByTestId('verdict');
		await expect.element(badge).toHaveTextContent('Accepted');
		await expect.element(badge).toHaveAttribute('data-tone', 'success');
		await expect.element(badge).toHaveAttribute('aria-busy', 'false');
	});

	it('colours failures differently', async () => {
		render(VerdictBadge, { status: SubmissionStatus.FINISHED, verdict: Verdict.WRONG_ANSWER });
		const badge = page.getByTestId('verdict');
		await expect.element(badge).toHaveTextContent('Wrong Answer');
		await expect.element(badge).toHaveAttribute('data-tone', 'danger');
	});

	it('shows the status (busy) while judging', async () => {
		render(VerdictBadge, { status: SubmissionStatus.JUDGING, verdict: Verdict.UNSPECIFIED });
		const badge = page.getByTestId('verdict');
		await expect.element(badge).toHaveTextContent('Judging');
		await expect.element(badge).toHaveAttribute('aria-busy', 'true');
	});

	it('reports broken judging', async () => {
		render(VerdictBadge, { status: SubmissionStatus.FAILED, verdict: Verdict.UNSPECIFIED });
		await expect.element(page.getByTestId('verdict')).toHaveTextContent('Judging failed');
	});
});

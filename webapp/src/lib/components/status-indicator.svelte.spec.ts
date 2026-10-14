import { create } from '@bufbuild/protobuf';
import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { GetStatusResponseSchema } from '#lib/gen/oj/v1/judge_pb.js';
import StatusIndicator from './status-indicator.svelte';

describe('status-indicator.svelte', () => {
	it('shows runners and queue depth when healthy', async () => {
		const status = create(GetStatusResponseSchema, { healthy: true, runners: 2, queueDepth: 3n });
		render(StatusIndicator, { status });
		await expect
			.element(page.getByTestId('judge-status'))
			.toHaveTextContent('2 runners · 3 queued');
	});

	it('shows degraded and offline states', async () => {
		const status = create(GetStatusResponseSchema, { healthy: false, broker: 'error: down' });
		const { rerender } = render(StatusIndicator, { status });
		await expect.element(page.getByTestId('judge-status')).toHaveTextContent('Degraded');
		await rerender({ status: null, error: 'The judge is unreachable' });
		await expect.element(page.getByTestId('judge-status')).toHaveTextContent('Judge offline');
	});
});

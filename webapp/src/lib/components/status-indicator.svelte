<script lang="ts">
	import type { GetStatusResponse } from '#lib/gen/oj/v1/judge_pb.js';
	import { cn } from '#lib/utils.js';

	/** `null` while loading; `error` when the judge could not be reached. */
	let { status, error = null }: { status: GetStatusResponse | null; error?: string | null } =
		$props();

	const state = $derived.by(() => {
		if (error) return { dot: 'bg-red-500', text: 'Judge offline', title: error };
		if (!status) return { dot: 'bg-muted-foreground/40', text: 'Checking…', title: '' };
		const runners = `${status.runners} runner${status.runners === 1 ? '' : 's'}`;
		const queue = `${status.queueDepth} queued`;
		if (!status.healthy) {
			return {
				dot: 'bg-red-500',
				text: 'Degraded',
				title: `dao: ${status.dao || '?'} · broker: ${status.broker || '?'}`
			};
		}
		return {
			dot: status.runners > 0 ? 'bg-green-500' : 'bg-amber-500',
			text: `${runners} · ${queue}`,
			title: status.runners > 0 ? 'Judge healthy' : 'No runner online: submissions will wait'
		};
	});
</script>

<span
	class="inline-flex items-center gap-2 text-xs text-muted-foreground"
	title={state.title}
	data-testid="judge-status"
	role="status"
>
	<span class={cn('size-2 rounded-full', state.dot)} aria-hidden="true"></span>
	<span><span class="sr-only">Judge status: </span>{state.text}</span>
</span>

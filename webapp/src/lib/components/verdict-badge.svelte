<script lang="ts">
	import LoaderIcon from '@lucide/svelte/icons/loader-circle';
	import { Badge } from '#lib/components/ui/badge/index.js';
	import type { SubmissionStatus, Verdict } from '#lib/gen/oj/v1/types_pb.js';
	import { isFinal, submissionLabel, TONE_CLASSES } from '#lib/labels.js';
	import { cn } from '#lib/utils.js';

	let {
		status,
		verdict,
		class: className
	}: { status: SubmissionStatus; verdict: Verdict; class?: string } = $props();

	const label = $derived(submissionLabel({ status, verdict }));
	const busy = $derived(!isFinal(status));
</script>

<Badge
	variant="secondary"
	class={cn(TONE_CLASSES[label.tone], className)}
	data-testid="verdict"
	data-tone={label.tone}
	aria-busy={busy}
>
	{#if busy}<LoaderIcon class="animate-spin" aria-hidden="true" />{/if}
	{label.label}
</Badge>

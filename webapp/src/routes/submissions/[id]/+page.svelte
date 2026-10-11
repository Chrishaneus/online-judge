<script lang="ts">
	import { timestampDate } from '@bufbuild/protobuf/wkt';
	import { invalidate } from '$app/navigation';
	import { resolve } from '$app/paths';
	import CopyButton from '#lib/components/copy-button.svelte';
	import TestResults from '#lib/components/test-results.svelte';
	import VerdictBadge from '#lib/components/verdict-badge.svelte';
	import * as Card from '#lib/components/ui/card/index.js';
	import { Verdict } from '#lib/gen/oj/v1/types_pb.js';
	import { isFinal, languageName } from '#lib/labels.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const sub = $derived(data.submission);
	const done = $derived(isFinal(sub.status));

	// Poll every second while PENDING / JUDGING; stop when judged (or after 5 minutes).
	$effect(() => {
		if (done) return;
		const started = Date.now();
		const timer = setInterval(() => {
			if (Date.now() - started > 5 * 60_000) clearInterval(timer);
			else invalidate('app:submission');
		}, 1000);
		return () => clearInterval(timer);
	});
</script>

<svelte:head><title>Submission #{sub.id} · Online Judge</title></svelte:head>

<h1 class="mb-4 text-2xl font-semibold">Submission #{sub.id}</h1>

<div class="space-y-6">
	<Card.Root>
		<Card.Header>
			<div class="flex flex-wrap items-center gap-3" aria-live="polite">
				<VerdictBadge status={sub.status} verdict={sub.verdict} class="h-6 px-3 text-sm" />
				{#if done}
					<span data-testid="tests-passed">{sub.passed}/{sub.total} tests passed</span>
					{#if sub.timeMs}<span class="text-muted-foreground">{sub.timeMs} ms</span>{/if}
				{:else}
					<span class="text-sm text-muted-foreground">Waiting for the judge…</span>
				{/if}
			</div>
			<Card.Description>
				Problem
				<a href={resolve('/problems/[id]', { id: String(sub.problemId) })} class="hover:underline"
					>#{sub.problemId}</a
				>
				· {sub.username || 'anonymous'} · {languageName(data.languages, sub.language)}
				{#if sub.createTime}· {timestampDate(sub.createTime).toLocaleString()}{/if}
			</Card.Description>
		</Card.Header>
		{#if sub.message || sub.results.length}
			<Card.Content class="space-y-4">
				{#if sub.message}
					{#if sub.verdict === Verdict.COMPILATION_ERROR}
						<pre class="code-block" data-testid="submission-message">{sub.message}</pre>
					{:else}
						<p data-testid="submission-message">{sub.message}</p>
					{/if}
				{/if}
				{#if sub.results.length}
					<TestResults results={sub.results} />
				{/if}
			</Card.Content>
		{/if}
	</Card.Root>

	<section aria-labelledby="source-heading">
		<div class="mb-2 flex items-center gap-2">
			<h2 id="source-heading" class="text-lg font-semibold">Source</h2>
			<CopyButton text={sub.source} label="Copy source code" />
		</div>
		<pre class="code-block max-h-[70vh]" data-testid="submission-source"><code>{sub.source}</code
			></pre>
	</section>
</div>

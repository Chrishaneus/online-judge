<script lang="ts">
	import type { RunCodeResponse } from '#lib/gen/oj/v1/judge_pb.js';
	import { RunStatus } from '#lib/gen/oj/v1/types_pb.js';
	import { formatMemoryKb, runStatusLabel } from '#lib/labels.js';
	import ToneBadge from './tone-badge.svelte';

	let { result }: { result: RunCodeResponse } = $props();
	const compileError = $derived(result.status === RunStatus.COMPILATION_ERROR);
</script>

<section class="space-y-2" aria-label="Run result" data-testid="run-result">
	<div class="flex flex-wrap items-center gap-2 text-sm">
		<ToneBadge label={runStatusLabel(result.status)} />
		{#if !compileError}
			<span class="text-muted-foreground">
				{result.timeMs} ms · {formatMemoryKb(result.memoryKb)} · exit code {result.exitCode}
			</span>
		{/if}
	</div>
	{#if result.compileOutput}
		<h3 class="text-xs font-medium text-muted-foreground">Compiler output</h3>
		<pre class="code-block" data-testid="run-compile-output">{result.compileOutput}</pre>
	{/if}
	{#if !compileError}
		<h3 class="text-xs font-medium text-muted-foreground">stdout</h3>
		<pre class="code-block" data-testid="run-stdout">{result.stdout || ' '}</pre>
		{#if result.stderr}
			<h3 class="text-xs font-medium text-muted-foreground">stderr</h3>
			<pre class="code-block text-destructive" data-testid="run-stderr">{result.stderr}</pre>
		{/if}
	{/if}
</section>

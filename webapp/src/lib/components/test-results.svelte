<script lang="ts">
	import * as Table from '#lib/components/ui/table/index.js';
	import type { TestResult } from '#lib/gen/oj/v1/types_pb.js';
	import { formatMemoryKb, verdictLabel } from '#lib/labels.js';
	import ToneBadge from './tone-badge.svelte';

	let { results }: { results: readonly TestResult[] } = $props();
</script>

<Table.Root data-testid="test-results">
	<Table.Header>
		<Table.Row>
			<Table.Head class="w-16 text-right">Test</Table.Head>
			<Table.Head>Verdict</Table.Head>
			<Table.Head class="text-right">Time</Table.Head>
			<Table.Head class="text-right">Memory</Table.Head>
		</Table.Row>
	</Table.Header>
	<Table.Body>
		{#each results as t (t.test)}
			<Table.Row>
				<Table.Cell class="text-right tabular-nums">
					{t.test}{#if t.sample}<span class="ml-1 text-xs text-muted-foreground">(sample)</span
						>{/if}
				</Table.Cell>
				<Table.Cell><ToneBadge label={verdictLabel(t.verdict)} /></Table.Cell>
				<Table.Cell class="text-right tabular-nums">{t.timeMs} ms</Table.Cell>
				<Table.Cell class="text-right tabular-nums">{formatMemoryKb(t.memoryKb)}</Table.Cell>
			</Table.Row>
		{/each}
	</Table.Body>
</Table.Root>

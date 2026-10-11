<script lang="ts">
	import { resolve } from '$app/paths';
	import ToneBadge from '#lib/components/tone-badge.svelte';
	import * as Empty from '#lib/components/ui/empty/index.js';
	import * as Table from '#lib/components/ui/table/index.js';
	import { difficultyLabel } from '#lib/labels.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<svelte:head><title>Problems · Online Judge</title></svelte:head>

<div class="mb-4 flex flex-wrap items-baseline gap-2">
	<h1 class="text-2xl font-semibold">Problems</h1>
	<span class="ml-auto text-sm text-muted-foreground">
		{data.problems.length} problem{data.problems.length === 1 ? '' : 's'}
	</span>
</div>
<p class="mb-4 text-muted-foreground">
	Pick a problem, write a solution, and submit it for judging.
</p>

{#if data.problems.length === 0}
	<Empty.Root class="border">
		<Empty.Header>
			<Empty.Title>No problems yet</Empty.Title>
			<Empty.Description>An admin can add some on the Admin page.</Empty.Description>
		</Empty.Header>
	</Empty.Root>
{:else}
	<div class="rounded-lg border">
		<Table.Root data-testid="problems">
			<Table.Header>
				<Table.Row>
					<Table.Head class="w-12 text-right">#</Table.Head>
					<Table.Head>Title</Table.Head>
					<Table.Head>Difficulty</Table.Head>
					<Table.Head class="hidden text-right sm:table-cell">Time limit</Table.Head>
					<Table.Head class="hidden text-right sm:table-cell">Memory</Table.Head>
					<Table.Head class="hidden md:table-cell"><span class="sr-only">Links</span></Table.Head>
				</Table.Row>
			</Table.Header>
			<Table.Body>
				{#each data.problems as p (p.id)}
					<Table.Row>
						<Table.Cell class="text-right text-muted-foreground tabular-nums">{p.id}</Table.Cell>
						<Table.Cell>
							<a
								href={resolve('/problems/[id]', { id: String(p.id) })}
								class="font-medium hover:underline">{p.title}</a
							>
						</Table.Cell>
						<Table.Cell><ToneBadge label={difficultyLabel(p.difficulty)} /></Table.Cell>
						<Table.Cell class="hidden text-right tabular-nums sm:table-cell"
							>{p.timeLimitMs} ms</Table.Cell
						>
						<Table.Cell class="hidden text-right tabular-nums sm:table-cell"
							>{p.memoryLimitMb} MB</Table.Cell
						>
						<Table.Cell class="hidden md:table-cell">
							<a
								href={resolve(`/submissions?problem=${p.id}`)}
								class="text-sm text-muted-foreground hover:underline">submissions</a
							>
						</Table.Cell>
					</Table.Row>
				{/each}
			</Table.Body>
		</Table.Root>
	</div>
{/if}

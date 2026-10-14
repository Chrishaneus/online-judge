<script lang="ts">
	import { timestampDate } from '@bufbuild/protobuf/wkt';
	import { onMount } from 'svelte';
	import { invalidate } from '$app/navigation';
	import { resolve } from '$app/paths';
	import VerdictBadge from '#lib/components/verdict-badge.svelte';
	import { Button } from '#lib/components/ui/button/index.js';
	import * as Empty from '#lib/components/ui/empty/index.js';
	import { Input } from '#lib/components/ui/input/index.js';
	import { Label } from '#lib/components/ui/label/index.js';
	import * as Table from '#lib/components/ui/table/index.js';
	import { browserStore, loadUsername } from '#lib/drafts.js';
	import { isFinal, languageName, timeAgo } from '#lib/labels.js';
	import { query } from '#lib/url.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	let myName = $state('');
	onMount(() => (myName = loadUsername(browserStore())));

	// Keep refreshing while anything on this page is still being judged.
	const anyPending = $derived(data.submissions.some((s) => !isFinal(s.status)));
	$effect(() => {
		if (!anyPending) return;
		const timer = setInterval(() => invalidate('app:submissions'), 1500);
		return () => clearInterval(timer);
	});

	const pageHref = (n: number) =>
		resolve(
			`/submissions${query({
				user: data.filter.username,
				problem: data.filter.problemId,
				page: n > 1 ? n : null
			})}`
		);
	const mineHref = $derived(
		resolve(`/submissions${query({ user: myName, problem: data.filter.problemId })}`)
	);
</script>

<svelte:head><title>Submissions · Online Judge</title></svelte:head>

<h1 class="mb-4 text-2xl font-semibold">Submissions</h1>

<form method="GET" class="mb-4 flex flex-wrap items-end gap-3" data-sveltekit-keepfocus>
	<div class="grid gap-1.5">
		<Label for="filter-user">User</Label>
		<Input
			id="filter-user"
			name="user"
			class="w-44"
			maxlength={32}
			placeholder="any user"
			value={data.filter.username}
		/>
	</div>
	<div class="grid gap-1.5">
		<Label for="filter-problem">Problem #</Label>
		<Input
			id="filter-problem"
			name="problem"
			type="number"
			min="1"
			class="w-28"
			placeholder="any"
			value={data.filter.problemId ?? ''}
		/>
	</div>
	<Button type="submit" variant="secondary">Filter</Button>
	{#if myName}
		<Button href={mineHref} variant="link">Only mine ({myName})</Button>
	{/if}
	{#if data.filter.username || data.filter.problemId}
		<Button href={resolve('/submissions')} variant="link">Clear</Button>
	{/if}
</form>

{#if data.submissions.length === 0}
	<Empty.Root class="border">
		<Empty.Header>
			<Empty.Title>No submissions found</Empty.Title>
			<Empty.Description>Solve a problem and your submission will show up here.</Empty.Description>
		</Empty.Header>
	</Empty.Root>
{:else}
	<div class="rounded-lg border">
		<Table.Root data-testid="submissions">
			<Table.Header>
				<Table.Row>
					<Table.Head class="text-right">#</Table.Head>
					<Table.Head>Problem</Table.Head>
					<Table.Head>User</Table.Head>
					<Table.Head class="hidden sm:table-cell">Language</Table.Head>
					<Table.Head>Verdict</Table.Head>
					<Table.Head class="text-right">Tests</Table.Head>
					<Table.Head class="hidden text-right sm:table-cell">Time</Table.Head>
					<Table.Head class="hidden md:table-cell">When</Table.Head>
				</Table.Row>
			</Table.Header>
			<Table.Body>
				{#each data.submissions as s (s.id)}
					{@const done = isFinal(s.status)}
					<Table.Row>
						<Table.Cell class="text-right tabular-nums">
							<a href={resolve('/submissions/[id]', { id: String(s.id) })} class="hover:underline"
								>{s.id}</a
							>
						</Table.Cell>
						<Table.Cell>
							<a
								href={resolve('/problems/[id]', { id: String(s.problemId) })}
								class="hover:underline">{s.problemId}</a
							>
						</Table.Cell>
						<Table.Cell class="max-w-32 truncate">{s.username || 'anonymous'}</Table.Cell>
						<Table.Cell class="hidden sm:table-cell"
							>{languageName(data.languages, s.language)}</Table.Cell
						>
						<Table.Cell><VerdictBadge status={s.status} verdict={s.verdict} /></Table.Cell>
						<Table.Cell class="text-right tabular-nums"
							>{done ? `${s.passed}/${s.total}` : '–'}</Table.Cell
						>
						<Table.Cell class="hidden text-right tabular-nums sm:table-cell"
							>{done ? `${s.timeMs} ms` : '–'}</Table.Cell
						>
						<Table.Cell
							class="hidden text-muted-foreground md:table-cell"
							title={s.createTime ? timestampDate(s.createTime).toLocaleString() : undefined}
						>
							{s.createTime ? timeAgo(timestampDate(s.createTime)) : ''}
						</Table.Cell>
					</Table.Row>
				{/each}
			</Table.Body>
		</Table.Root>
	</div>
{/if}

{#if data.page > 1 || data.hasNext}
	<nav aria-label="Pagination" class="mt-4 flex items-center justify-between gap-2">
		<Button
			href={data.page > 1 ? pageHref(data.page - 1) : undefined}
			variant="outline"
			disabled={data.page <= 1}
		>
			Previous
		</Button>
		<span class="text-sm text-muted-foreground">Page {data.page}</span>
		<Button
			href={data.hasNext ? pageHref(data.page + 1) : undefined}
			variant="outline"
			disabled={!data.hasNext}
		>
			Next
		</Button>
	</nav>
{/if}

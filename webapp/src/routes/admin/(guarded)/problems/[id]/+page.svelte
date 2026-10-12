<script lang="ts">
	import PlusIcon from '@lucide/svelte/icons/plus';
	import TrashIcon from '@lucide/svelte/icons/trash-2';
	import { toast } from 'svelte-sonner';
	import { onMount } from 'svelte';
	import { enhance } from '$app/forms';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import TestCaseFields from '#lib/components/test-case-fields.svelte';
	import ToneBadge from '#lib/components/tone-badge.svelte';
	import * as Alert from '#lib/components/ui/alert/index.js';
	import { Badge } from '#lib/components/ui/badge/index.js';
	import { Button } from '#lib/components/ui/button/index.js';
	import * as Card from '#lib/components/ui/card/index.js';
	import * as Empty from '#lib/components/ui/empty/index.js';
	import { difficultyLabel } from '#lib/labels.js';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	let input = $state('');
	let expected = $state('');
	let sample = $state(false);
	let adding = $state(false);

	onMount(() => {
		if (page.url.searchParams.get('created')) toast.success(`Created "${data.problem.title}"`);
	});
</script>

<svelte:head><title>{data.problem.title} · Test cases · Admin · Online Judge</title></svelte:head>

<div class="mb-4 flex flex-wrap items-center gap-3">
	<h2 class="text-lg font-semibold">
		<a href={resolve('/problems/[id]', { id: String(data.problem.id) })} class="hover:underline"
			>{data.problem.title}</a
		>
	</h2>
	<ToneBadge label={difficultyLabel(data.problem.difficulty)} />
	<span class="text-sm text-muted-foreground">
		{data.problem.slug} · {data.problem.timeLimitMs} ms · {data.problem.memoryLimitMb} MB
	</span>
</div>

{#if form?.error}
	<Alert.Root variant="destructive" class="mb-4" data-testid="admin-error">
		<Alert.Title>{form.error}</Alert.Title>
	</Alert.Root>
{/if}

<h3 class="mb-2 font-semibold">Test cases ({data.testCases.length})</h3>
{#if data.testCases.length === 0}
	<Empty.Root class="mb-6 border">
		<Empty.Header>
			<Empty.Title>No test cases</Empty.Title>
			<Empty.Description>Submissions can't be judged until you add one.</Empty.Description>
		</Empty.Header>
	</Empty.Root>
{:else}
	<ol class="mb-6 space-y-3" data-testid="test-cases">
		{#each data.testCases as tc (tc.id)}
			<li>
				<Card.Root class="gap-3 py-3">
					<Card.Header class="flex flex-row items-center gap-2 px-3">
						<span class="font-medium">#{tc.ordinal}</span>
						{#if tc.isSample}<Badge variant="outline">sample</Badge>{/if}
						<form
							method="POST"
							action="?/delete"
							class="ml-auto"
							use:enhance={({ cancel }) => {
								if (!confirm(`Delete test case #${tc.ordinal}?`)) return cancel();
							}}
						>
							<input type="hidden" name="id" value={tc.id} />
							<Button
								type="submit"
								variant="destructive"
								size="sm"
								aria-label={`Delete test case ${tc.ordinal}`}
							>
								<TrashIcon aria-hidden="true" /> Delete
							</Button>
						</form>
					</Card.Header>
					<Card.Content class="grid gap-3 px-3 sm:grid-cols-2">
						<div class="min-w-0">
							<div class="mb-1 text-xs text-muted-foreground">Input</div>
							<pre class="code-block max-h-48">{tc.input}</pre>
						</div>
						<div class="min-w-0">
							<div class="mb-1 text-xs text-muted-foreground">Expected output</div>
							<pre class="code-block max-h-48">{tc.expectedOutput}</pre>
						</div>
					</Card.Content>
				</Card.Root>
			</li>
		{/each}
	</ol>
{/if}

<form
	method="POST"
	action="?/add"
	class="space-y-3"
	use:enhance={() => {
		adding = true;
		return async ({ result, update }) => {
			await update({ reset: false });
			adding = false;
			if (result.type === 'success') {
				input = '';
				expected = '';
				sample = false;
				toast.success('Test case added');
			}
		};
	}}
>
	<h3 class="font-semibold">Add a test case</h3>
	<TestCaseFields
		index={0}
		number={data.testCases.length + 1}
		bind:input
		bind:expected
		bind:sample
	/>
	<Button type="submit" disabled={adding}><PlusIcon aria-hidden="true" /> Add test case</Button>
</form>

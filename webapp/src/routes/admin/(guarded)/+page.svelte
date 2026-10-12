<script lang="ts">
	import TrashIcon from '@lucide/svelte/icons/trash-2';
	import { toast } from 'svelte-sonner';
	import { enhance } from '$app/forms';
	import { resolve } from '$app/paths';
	import ToneBadge from '#lib/components/tone-badge.svelte';
	import * as Alert from '#lib/components/ui/alert/index.js';
	import { Button } from '#lib/components/ui/button/index.js';
	import * as Empty from '#lib/components/ui/empty/index.js';
	import * as Table from '#lib/components/ui/table/index.js';
	import { difficultyLabel } from '#lib/labels.js';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
</script>

<svelte:head><title>Admin · Online Judge</title></svelte:head>

<h2 class="mb-3 text-lg font-semibold">Problems</h2>

{#if form?.error}
	<Alert.Root variant="destructive" class="mb-4" data-testid="admin-error">
		<Alert.Title>{form.error}</Alert.Title>
	</Alert.Root>
{/if}

{#if data.problems.length === 0}
	<Empty.Root class="border">
		<Empty.Header>
			<Empty.Title>No problems</Empty.Title>
			<Empty.Description>Create the first one.</Empty.Description>
		</Empty.Header>
		<Empty.Content>
			<Button href={resolve('/admin/(guarded)/problems/new')}>New problem</Button>
		</Empty.Content>
	</Empty.Root>
{:else}
	<div class="rounded-lg border">
		<Table.Root data-testid="admin-problems">
			<Table.Header>
				<Table.Row>
					<Table.Head class="w-12 text-right">#</Table.Head>
					<Table.Head class="hidden sm:table-cell">Slug</Table.Head>
					<Table.Head>Title</Table.Head>
					<Table.Head class="hidden sm:table-cell">Difficulty</Table.Head>
					<Table.Head class="text-right">Actions</Table.Head>
				</Table.Row>
			</Table.Header>
			<Table.Body>
				{#each data.problems as p (p.id)}
					<Table.Row>
						<Table.Cell class="text-right tabular-nums">{p.id}</Table.Cell>
						<Table.Cell class="hidden font-mono text-xs sm:table-cell">{p.slug}</Table.Cell>
						<Table.Cell>
							<a href={resolve('/problems/[id]', { id: String(p.id) })} class="hover:underline"
								>{p.title}</a
							>
						</Table.Cell>
						<Table.Cell class="hidden sm:table-cell">
							<ToneBadge label={difficultyLabel(p.difficulty)} />
						</Table.Cell>
						<Table.Cell class="text-right">
							<div class="flex justify-end gap-1">
								<Button
									href={resolve('/admin/(guarded)/problems/[id]', { id: String(p.id) })}
									variant="ghost"
									size="sm">Test cases</Button
								>
								<form
									method="POST"
									action="?/delete"
									use:enhance={({ cancel }) => {
										if (!confirm(`Delete "${p.title}" and all its submissions?`)) return cancel();
										return async ({ result, update }) => {
											await update();
											if (result.type === 'success') toast.success(`Deleted "${p.title}"`);
										};
									}}
								>
									<input type="hidden" name="id" value={p.id} />
									<input type="hidden" name="title" value={p.title} />
									<Button
										type="submit"
										variant="destructive"
										size="sm"
										aria-label={`Delete ${p.title}`}
									>
										<TrashIcon aria-hidden="true" /> Delete
									</Button>
								</form>
							</div>
						</Table.Cell>
					</Table.Row>
				{/each}
			</Table.Body>
		</Table.Root>
	</div>
{/if}

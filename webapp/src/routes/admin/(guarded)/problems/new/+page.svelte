<script lang="ts">
	import PlusIcon from '@lucide/svelte/icons/plus';
	import { enhance } from '$app/forms';
	import Markdown from '#lib/components/markdown.svelte';
	import TestCaseFields from '#lib/components/test-case-fields.svelte';
	import * as Alert from '#lib/components/ui/alert/index.js';
	import { Button } from '#lib/components/ui/button/index.js';
	import * as Card from '#lib/components/ui/card/index.js';
	import * as Field from '#lib/components/ui/field/index.js';
	import { Input } from '#lib/components/ui/input/index.js';
	import * as NativeSelect from '#lib/components/ui/native-select/index.js';
	import { Textarea } from '#lib/components/ui/textarea/index.js';
	import { SLUG_PATTERN } from '#lib/admin-form.js';
	import { DIFFICULTY_OPTIONS, difficultyLabel } from '#lib/labels.js';
	import type { PageProps } from './$types';

	let { form }: PageProps = $props();

	let nextKey = 0;
	const row = (sample = false) => ({ key: nextKey++, input: '', expected: '', sample });
	let testCases = $state([row(true), row()]);
	let statement = $state('');
	let preview = $state(false);
	let submitting = $state(false);
	const errors = $derived(form?.errors ?? {});
</script>

<svelte:head><title>New problem · Admin · Online Judge</title></svelte:head>

<form
	method="POST"
	use:enhance={() => {
		submitting = true;
		return async ({ update }) => {
			await update({ reset: false });
			submitting = false;
		};
	}}
>
	<Card.Root>
		<Card.Header>
			<Card.Title><h2 class="text-lg">New problem</h2></Card.Title>
		</Card.Header>
		<Card.Content>
			<Field.Group>
				{#if form?.error}
					<Alert.Root variant="destructive" data-testid="create-error">
						<Alert.Title>{form.error}</Alert.Title>
					</Alert.Root>
				{/if}
				<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
					<Field.Field class="lg:col-span-2" data-invalid={errors.slug ? true : undefined}>
						<Field.Label for="slug">Slug</Field.Label>
						<Input
							id="slug"
							name="slug"
							required
							maxlength={64}
							pattern={SLUG_PATTERN}
							placeholder="two-sum"
							aria-invalid={errors.slug ? true : undefined}
						/>
						{#if errors.slug}<Field.Error>{errors.slug}</Field.Error>{/if}
					</Field.Field>
					<Field.Field class="lg:col-span-3" data-invalid={errors.title ? true : undefined}>
						<Field.Label for="title">Title</Field.Label>
						<Input
							id="title"
							name="title"
							required
							maxlength={200}
							placeholder="Two Sum"
							aria-invalid={errors.title ? true : undefined}
						/>
						{#if errors.title}<Field.Error>{errors.title}</Field.Error>{/if}
					</Field.Field>
					<Field.Field>
						<Field.Label for="difficulty">Difficulty</Field.Label>
						<NativeSelect.Root id="difficulty" name="difficulty" class="w-full">
							{#each DIFFICULTY_OPTIONS as d (d)}
								<NativeSelect.Option value={String(d)}
									>{difficultyLabel(d).label}</NativeSelect.Option
								>
							{/each}
						</NativeSelect.Root>
					</Field.Field>
					<Field.Field data-invalid={errors.timeLimitMs ? true : undefined}>
						<Field.Label for="timeLimitMs">Time limit (ms)</Field.Label>
						<Input
							id="timeLimitMs"
							name="timeLimitMs"
							type="number"
							min="100"
							max="15000"
							value="1000"
						/>
						{#if errors.timeLimitMs}<Field.Error>{errors.timeLimitMs}</Field.Error>{/if}
					</Field.Field>
					<Field.Field data-invalid={errors.memoryLimitMb ? true : undefined}>
						<Field.Label for="memoryLimitMb">Memory limit (MB)</Field.Label>
						<Input
							id="memoryLimitMb"
							name="memoryLimitMb"
							type="number"
							min="16"
							max="1024"
							value="256"
						/>
						{#if errors.memoryLimitMb}<Field.Error>{errors.memoryLimitMb}</Field.Error>{/if}
					</Field.Field>
				</div>

				<Field.Field data-invalid={errors.statement ? true : undefined}>
					<div class="flex items-center">
						<Field.Label for="statement">Statement (Markdown)</Field.Label>
						<Button variant="link" size="sm" class="ml-auto" onclick={() => (preview = !preview)}>
							{preview ? 'Hide preview' : 'Preview'}
						</Button>
					</div>
					<Textarea
						id="statement"
						name="statement"
						rows={10}
						class="field-sizing-fixed font-mono text-[13px]"
						placeholder="Markdown statement. Use ### Input / ### Output sections."
						bind:value={statement}
						aria-invalid={errors.statement ? true : undefined}
					/>
					{#if errors.statement}<Field.Error>{errors.statement}</Field.Error>{/if}
					{#if preview}
						<div class="rounded-lg border p-4" aria-label="Statement preview">
							<Markdown source={statement} />
						</div>
					{/if}
				</Field.Field>

				<Field.Set>
					<Field.Legend>Test cases</Field.Legend>
					{#if errors.testCases}
						<p class="text-sm text-destructive" role="alert">{errors.testCases}</p>
					{/if}
					<div class="space-y-3">
						{#each testCases as tc, i (tc.key)}
							<TestCaseFields
								index={i}
								bind:input={tc.input}
								bind:expected={tc.expected}
								bind:sample={tc.sample}
								onremove={testCases.length > 1
									? () => (testCases = testCases.filter((t) => t.key !== tc.key))
									: undefined}
							/>
						{/each}
					</div>
					<div class="flex flex-wrap gap-2">
						<Button variant="outline" onclick={() => testCases.push(row())}>
							<PlusIcon aria-hidden="true" /> Add test case
						</Button>
						<Button type="submit" class="ml-auto" disabled={submitting}>
							{submitting ? 'Creating…' : 'Create problem'}
						</Button>
					</div>
				</Field.Set>
			</Field.Group>
		</Card.Content>
	</Card.Root>
</form>

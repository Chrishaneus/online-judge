<script lang="ts">
	import ClockIcon from '@lucide/svelte/icons/clock';
	import CpuIcon from '@lucide/svelte/icons/cpu';
	import PlayIcon from '@lucide/svelte/icons/play';
	import SendIcon from '@lucide/svelte/icons/send';
	import { untrack } from 'svelte';
	import { enhance } from '$app/forms';
	import { resolve } from '$app/paths';
	import CodeEditor from '#lib/components/code-editor.svelte';
	import CopyButton from '#lib/components/copy-button.svelte';
	import Markdown from '#lib/components/markdown.svelte';
	import RunResult from '#lib/components/run-result.svelte';
	import ToneBadge from '#lib/components/tone-badge.svelte';
	import * as Alert from '#lib/components/ui/alert/index.js';
	import { Button } from '#lib/components/ui/button/index.js';
	import * as Card from '#lib/components/ui/card/index.js';
	import { Input } from '#lib/components/ui/input/index.js';
	import { Label } from '#lib/components/ui/label/index.js';
	import * as NativeSelect from '#lib/components/ui/native-select/index.js';
	import { Spinner } from '#lib/components/ui/spinner/index.js';
	import { Textarea } from '#lib/components/ui/textarea/index.js';
	import {
		browserStore,
		loadDraft,
		loadLanguage,
		loadUsername,
		sanitizeUsername,
		saveDraft,
		saveLanguage,
		saveUsername,
		template
	} from '#lib/drafts.js';
	import { Language } from '#lib/gen/oj/v1/types_pb.js';
	import { difficultyLabel, parseLanguage } from '#lib/labels.js';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	const problem = $derived(data.problem);
	const available = $derived(data.languages.map((l) => l.language));

	// Editor state. SSR renders the first language's template; drafts load on mount.
	const initial = (() => {
		const lang = data.languages[0]?.language ?? Language.PYTHON;
		return { lang, stdin: data.problem.samples[0]?.input ?? '' };
	})();
	let languageValue = $state(String(initial.lang));
	const language = $derived(parseLanguage(languageValue) ?? Language.PYTHON);
	let source = $state(template(initial.lang));
	let stdin = $state(initial.stdin);
	let username = $state('');
	let pending = $state<'run' | 'submit' | null>(null);
	let formEl: HTMLFormElement | undefined = $state();
	let submitButton: HTMLButtonElement | null = $state(null);

	// Load the saved name, language and draft in the browser, and again whenever the
	// route switches to another problem (SvelteKit reuses this component).
	$effect(() => {
		const id = problem.id;
		untrack(() => {
			const store = browserStore();
			username = loadUsername(store);
			const lang = loadLanguage(store, available);
			languageValue = String(lang);
			source = loadDraft(store, id, lang);
			stdin = problem.samples[0]?.input ?? '';
		});
	});

	function changeLanguage() {
		const store = browserStore();
		saveLanguage(store, language);
		source = loadDraft(store, problem.id, language);
	}

	function resetTemplate() {
		if (!confirm('Replace your code with the starter template?')) return;
		source = template(language);
		saveDraft(browserStore(), problem.id, language, source);
	}
</script>

<svelte:head><title>{problem.title} · Online Judge</title></svelte:head>

<div class="grid gap-6 lg:grid-cols-2">
	<Card.Root class="min-w-0">
		<Card.Header>
			<div class="flex flex-wrap items-center gap-3">
				<h1 class="text-2xl font-semibold">{problem.title}</h1>
				<ToneBadge label={difficultyLabel(problem.difficulty)} />
			</div>
			<div class="flex flex-wrap gap-4 text-sm text-muted-foreground">
				<span class="inline-flex items-center gap-1">
					<ClockIcon class="size-4" aria-hidden="true" />
					<span class="sr-only">Time limit:</span>
					{problem.timeLimitMs} ms
				</span>
				<span class="inline-flex items-center gap-1">
					<CpuIcon class="size-4" aria-hidden="true" />
					<span class="sr-only">Memory limit:</span>
					{problem.memoryLimitMb} MB
				</span>
				<a href={resolve(`/submissions?problem=${problem.id}`)} class="hover:underline"
					>Submissions</a
				>
			</div>
		</Card.Header>
		<Card.Content class="space-y-6">
			<Markdown source={problem.statement} />

			{#if problem.samples.length}
				<section class="space-y-4" aria-labelledby="examples-heading">
					<h2 id="examples-heading" class="text-lg font-semibold">Examples</h2>
					{#each problem.samples as sample, i (i)}
						<div class="grid gap-3 sm:grid-cols-2" data-testid="sample">
							<div class="min-w-0">
								<div class="mb-1 flex items-center gap-1 text-sm font-medium">
									Input {i + 1}
									<span class="ml-auto"></span>
									<Button variant="ghost" size="xs" onclick={() => (stdin = sample.input)}>
										Use as input
									</Button>
									<CopyButton text={sample.input} label={`Copy sample input ${i + 1}`} />
								</div>
								<pre class="code-block">{sample.input}</pre>
							</div>
							<div class="min-w-0">
								<div class="mb-1 flex items-center gap-1 text-sm font-medium">
									Output {i + 1}
									<span class="ml-auto"></span>
									<CopyButton text={sample.output} label={`Copy sample output ${i + 1}`} />
								</div>
								<pre class="code-block">{sample.output}</pre>
							</div>
						</div>
					{/each}
				</section>
			{/if}
		</Card.Content>
	</Card.Root>

	<Card.Root class="min-w-0 self-start lg:sticky lg:top-20">
		<Card.Content>
			<form
				method="POST"
				action="?/submit"
				bind:this={formEl}
				class="space-y-4"
				use:enhance={({ action }) => {
					pending = action.search.includes('run') ? 'run' : 'submit';
					return async ({ update }) => {
						await update({ reset: false, invalidateAll: false });
						pending = null;
					};
				}}
			>
				<div class="flex flex-wrap items-end gap-3">
					<div class="grid gap-1.5">
						<Label for="language">Language</Label>
						<NativeSelect.Root
							id="language"
							name="language"
							bind:value={languageValue}
							onchange={changeLanguage}
						>
							{#each data.languages as l (l.language)}
								<NativeSelect.Option value={String(l.language)}>{l.name}</NativeSelect.Option>
							{/each}
						</NativeSelect.Root>
					</div>
					<div class="grid gap-1.5">
						<Label for="username">Your name</Label>
						<Input
							id="username"
							name="username"
							class="w-40"
							maxlength={32}
							placeholder="anonymous"
							autocomplete="nickname"
							spellcheck="false"
							bind:value={username}
							oninput={() => {
								username = sanitizeUsername(username);
								saveUsername(browserStore(), username);
							}}
						/>
					</div>
					<Button variant="link" size="sm" class="ml-auto" onclick={resetTemplate}>
						Reset to template
					</Button>
				</div>

				<div class="grid gap-1.5">
					<Label for="source">Source code</Label>
					<CodeEditor
						id="source"
						name="source"
						bind:value={source}
						onchange={(v) => saveDraft(browserStore(), problem.id, language, v)}
						onsubmitshortcut={() => formEl?.requestSubmit(submitButton)}
					/>
				</div>

				<div class="grid gap-1.5">
					<Label for="stdin">Custom input (for Run)</Label>
					<Textarea
						id="stdin"
						name="stdin"
						rows={4}
						spellcheck="false"
						class="field-sizing-fixed font-mono text-[13px]"
						bind:value={stdin}
					/>
				</div>

				<div class="flex flex-wrap justify-end gap-2">
					<Button type="submit" variant="outline" formaction="?/run" disabled={pending !== null}>
						{#if pending === 'run'}<Spinner />{:else}<PlayIcon aria-hidden="true" />{/if}
						Run
					</Button>
					<Button
						type="submit"
						formaction="?/submit"
						disabled={pending !== null}
						bind:ref={submitButton}
						title="Ctrl+Enter"
					>
						{#if pending === 'submit'}<Spinner />{:else}<SendIcon aria-hidden="true" />{/if}
						Submit
					</Button>
				</div>

				{#if form?.error}
					<Alert.Root variant="destructive" data-testid="editor-error">
						<Alert.Title>{form.action === 'run' ? 'Run failed' : 'Submission failed'}</Alert.Title>
						<Alert.Description>{form.error}</Alert.Description>
					</Alert.Root>
				{/if}
				{#if form && 'run' in form && form.run}
					<RunResult result={form.run} />
				{/if}
			</form>
		</Card.Content>
	</Card.Root>
</div>

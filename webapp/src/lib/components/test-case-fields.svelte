<script lang="ts">
	import XIcon from '@lucide/svelte/icons/x';
	import { Button } from '#lib/components/ui/button/index.js';
	import { Label } from '#lib/components/ui/label/index.js';
	import { Textarea } from '#lib/components/ui/textarea/index.js';

	/** One test case row of an admin form; posts tcInput / tcExpected / tcSample (= index). */
	let {
		index,
		number = index + 1,
		input = $bindable(''),
		expected = $bindable(''),
		sample = $bindable(false),
		onremove
	}: {
		index: number;
		number?: number;
		input?: string;
		expected?: string;
		sample?: boolean;
		onremove?: () => void;
	} = $props();

	const id = $props.id();
</script>

<fieldset class="grid gap-3 rounded-lg border p-3 sm:grid-cols-2" data-testid="test-case-row">
	<legend class="px-1 text-sm font-medium">Test case {number}</legend>
	<div class="grid min-w-0 gap-1.5">
		<Label for="{id}-input">Input</Label>
		<Textarea
			id="{id}-input"
			name="tcInput"
			rows={3}
			spellcheck="false"
			class="field-sizing-fixed font-mono text-[13px]"
			bind:value={input}
		/>
	</div>
	<div class="grid min-w-0 gap-1.5">
		<Label for="{id}-expected">Expected output</Label>
		<Textarea
			id="{id}-expected"
			name="tcExpected"
			rows={3}
			spellcheck="false"
			class="field-sizing-fixed font-mono text-[13px]"
			bind:value={expected}
		/>
	</div>
	<div class="flex items-center gap-2 sm:col-span-2">
		<input
			id="{id}-sample"
			type="checkbox"
			name="tcSample"
			value={String(index)}
			class="size-4 accent-primary"
			bind:checked={sample}
		/>
		<Label for="{id}-sample">Sample (shown on the problem page)</Label>
		{#if onremove}
			<Button variant="ghost" size="sm" class="ml-auto" onclick={onremove}>
				<XIcon aria-hidden="true" /> Remove
				<span class="sr-only">test case {number}</span>
			</Button>
		{/if}
	</div>
</fieldset>

<script lang="ts">
	import CheckIcon from '@lucide/svelte/icons/check';
	import CopyIcon from '@lucide/svelte/icons/copy';
	import { Button } from '#lib/components/ui/button/index.js';

	let { text, label = 'Copy' }: { text: string; label?: string } = $props();
	let copied = $state(false);

	async function copy() {
		try {
			await navigator.clipboard.writeText(text);
			copied = true;
			setTimeout(() => (copied = false), 1500);
		} catch {
			// Clipboard blocked (insecure context / permissions): nothing useful to do.
		}
	}
</script>

<Button variant="ghost" size="xs" onclick={copy} aria-label={label}>
	{#if copied}<CheckIcon aria-hidden="true" /> Copied{:else}<CopyIcon aria-hidden="true" /> Copy{/if}
</Button>

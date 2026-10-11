<script lang="ts">
	import { renderMarkdown } from '#lib/markdown.js';

	let { source }: { source: string } = $props();
	// renderMarkdown escapes all input before adding markup, so {@html} is safe here.
	const html = $derived(renderMarkdown(source));
</script>

<div class="markdown">
	<!-- eslint-disable-next-line svelte/no-at-html-tags -->
	{@html html}
</div>

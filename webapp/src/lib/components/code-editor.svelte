<script lang="ts">
	import { cn } from '#lib/utils.js';

	let {
		value = $bindable(''),
		id,
		name,
		label = 'Source code',
		rows = 18,
		indent = '    ',
		onchange,
		onsubmitshortcut,
		class: className
	}: {
		value?: string;
		id?: string;
		name?: string;
		/** Accessible name. */
		label?: string;
		rows?: number;
		indent?: string;
		/** Called after every edit (typing, Tab, Shift+Tab). */
		onchange?: (value: string) => void;
		/** Ctrl/Cmd+Enter. */
		onsubmitshortcut?: () => void;
		class?: string;
	} = $props();

	// After Escape, the next Tab moves focus instead of indenting (no keyboard trap).
	let tabMovesFocus = false;

	function commit(ta: HTMLTextAreaElement) {
		value = ta.value;
		onchange?.(value);
	}

	function onkeydown(e: KeyboardEvent) {
		const ta = e.currentTarget as HTMLTextAreaElement;
		if (e.key === 'Escape') {
			tabMovesFocus = true;
			return;
		}
		if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
			e.preventDefault();
			onsubmitshortcut?.();
			return;
		}
		if (e.key !== 'Tab' || e.ctrlKey || e.metaKey || e.altKey) {
			tabMovesFocus = false;
			return;
		}
		if (tabMovesFocus) {
			tabMovesFocus = false;
			return;
		}
		e.preventDefault();
		const { selectionStart: start, selectionEnd: end } = ta;
		if (!e.shiftKey && start === end) {
			ta.setRangeText(indent, start, end, 'end');
		} else {
			// Indent / dedent every line touched by the selection.
			const lineStart = ta.value.lastIndexOf('\n', start - 1) + 1;
			const block = ta.value.slice(lineStart, end);
			const lines = block.split('\n');
			const changed = lines.map((line) => {
				if (!e.shiftKey) return indent + line;
				if (line.startsWith(indent)) return line.slice(indent.length);
				return line.replace(/^[ \t]+/, '');
			});
			const replacement = changed.join('\n');
			const firstDelta = changed[0].length - lines[0].length;
			ta.setRangeText(replacement, lineStart, end, 'preserve');
			const newStart = Math.max(lineStart, start + firstDelta);
			const newEnd = start === end ? newStart : lineStart + replacement.length;
			ta.setSelectionRange(newStart, newEnd);
		}
		commit(ta);
	}
</script>

<textarea
	{id}
	{name}
	{rows}
	aria-label={label}
	aria-describedby={id ? `${id}-hint` : undefined}
	spellcheck="false"
	autocapitalize="off"
	autocomplete="off"
	wrap="off"
	data-testid="code-editor"
	class={cn(
		'w-full resize-y rounded-md border border-input bg-transparent px-3 py-2 font-mono text-[13px] leading-5 [tab-size:4] shadow-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30',
		className
	)}
	bind:value
	oninput={(e) => onchange?.((e.currentTarget as HTMLTextAreaElement).value)}
	{onkeydown}></textarea>
{#if id}
	<p id="{id}-hint" class="sr-only">
		Tab indents, Shift+Tab dedents, Escape then Tab leaves the editor, Ctrl+Enter submits.
	</p>
{/if}

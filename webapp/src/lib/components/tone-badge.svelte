<script lang="ts">
	import { Badge } from '#lib/components/ui/badge/index.js';
	import { TONE_CLASSES, type Label } from '#lib/labels.js';
	import { cn } from '#lib/utils.js';

	let {
		label,
		short = false,
		class: className
	}: {
		label: Label;
		/** Show the short code (AC, WA) and keep the full label as tooltip / accessible name. */
		short?: boolean;
		class?: string;
	} = $props();
</script>

<Badge
	variant="secondary"
	class={cn(TONE_CLASSES[label.tone], className)}
	title={label.label}
	aria-label={short ? label.label : undefined}
	data-tone={label.tone}
>
	{short ? label.short : label.label}
</Badge>

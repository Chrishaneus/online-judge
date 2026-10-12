<script lang="ts">
	import LogOutIcon from '@lucide/svelte/icons/log-out';
	import { resolve } from '$app/paths';
	import { Button } from '#lib/components/ui/button/index.js';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<div class="mb-6 flex flex-wrap items-center gap-2 border-b pb-3">
	<a href={resolve('/admin/(guarded)')} class="text-2xl font-semibold">Admin</a>
	<Button href={resolve('/admin/(guarded)/problems/new')} variant="outline" size="sm" class="ml-4">
		New problem
	</Button>
	<form method="POST" action={resolve('/admin/logout')} class="ml-auto">
		<Button type="submit" variant="ghost" size="sm"
			><LogOutIcon aria-hidden="true" /> Sign out</Button
		>
	</form>
</div>

{@render children()}

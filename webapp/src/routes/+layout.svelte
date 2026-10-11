<script lang="ts">
	import './layout.css';
	import { ModeWatcher } from 'mode-watcher';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import favicon from '#lib/assets/favicon.svg';
	import StatusIndicator from '#lib/components/status-indicator.svelte';
	import ThemeToggle from '#lib/components/theme-toggle.svelte';
	import { Toaster } from '#lib/components/ui/sonner/index.js';
	import { cn } from '#lib/utils.js';
	import type { LayoutProps } from './$types';

	let { children, data }: LayoutProps = $props();

	const nav = [
		{
			href: resolve('/'),
			label: 'Problems',
			match: (p: string) => p === '/' || p.startsWith('/problems')
		},
		{
			href: resolve('/submissions'),
			label: 'Submissions',
			match: (p: string) => p.startsWith('/submissions')
		},
		{
			href: resolve('/admin/(guarded)'),
			label: 'Admin',
			match: (p: string) => p.startsWith('/admin')
		}
	];
</script>

<ModeWatcher />
<Toaster richColors closeButton />

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>Online Judge</title>
	<meta
		name="description"
		content="Solve programming problems and get your code judged instantly."
	/>
</svelte:head>

<a
	href="#main"
	class="sr-only z-50 rounded-md bg-background px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
	>Skip to content</a
>

<div class="flex min-h-svh flex-col">
	<header class="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
		<div class="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2 sm:px-6">
			<a href={resolve('/')} class="flex items-center gap-2 font-semibold">
				<img src={favicon} alt="" class="size-5" />
				Online Judge
			</a>
			<nav aria-label="Main" class="order-last flex w-full gap-1 sm:order-none sm:w-auto sm:flex-1">
				{#each nav as item (item.href)}
					{@const active = item.match(page.url.pathname)}
					<a
						href={item.href}
						aria-current={active ? 'page' : undefined}
						class={cn(
							'rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground',
							active && 'bg-muted font-medium text-foreground'
						)}>{item.label}</a
					>
				{/each}
			</nav>
			<div class="ml-auto flex items-center gap-3">
				{#await data.judgeStatus}
					<StatusIndicator status={null} />
				{:then res}
					<StatusIndicator status={res.ok ? res.data : null} error={res.ok ? null : res.error} />
				{:catch}
					<StatusIndicator status={null} error="Status unavailable" />
				{/await}
				<ThemeToggle />
			</div>
		</div>
	</header>

	<main
		id="main"
		tabindex="-1"
		class="mx-auto w-full max-w-7xl flex-1 px-4 py-6 outline-none sm:px-6"
	>
		{@render children()}
	</main>

	<footer class="border-t py-4 text-center text-xs text-muted-foreground">Online Judge</footer>
</div>

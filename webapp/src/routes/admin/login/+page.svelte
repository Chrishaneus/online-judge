<script lang="ts">
	import { enhance } from '$app/forms';
	import * as Alert from '#lib/components/ui/alert/index.js';
	import { Button } from '#lib/components/ui/button/index.js';
	import * as Card from '#lib/components/ui/card/index.js';
	import { Input } from '#lib/components/ui/input/index.js';
	import { Label } from '#lib/components/ui/label/index.js';
	import type { PageProps } from './$types';

	let { form }: PageProps = $props();
	let submitting = $state(false);
</script>

<svelte:head><title>Admin sign in · Online Judge</title></svelte:head>

<Card.Root class="mx-auto mt-8 w-full max-w-sm">
	<Card.Header>
		<Card.Title><h1 class="text-xl">Admin sign in</h1></Card.Title>
		<Card.Description>Use the ADMIN_TOKEN configured for the api.</Card.Description>
	</Card.Header>
	<Card.Content>
		<form
			method="POST"
			class="space-y-4"
			use:enhance={() => {
				submitting = true;
				return async ({ update }) => {
					await update();
					submitting = false;
				};
			}}
		>
			{#if form?.error}
				<Alert.Root variant="destructive" data-testid="login-error">
					<Alert.Title>{form.error}</Alert.Title>
				</Alert.Root>
			{/if}
			<div class="grid gap-1.5">
				<Label for="token">Admin token</Label>
				<Input id="token" name="token" type="password" autocomplete="off" required />
			</div>
			<Button type="submit" class="w-full" disabled={submitting}>
				{submitting ? 'Checking…' : 'Sign in'}
			</Button>
		</form>
	</Card.Content>
</Card.Root>

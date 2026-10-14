<script lang="ts">
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { Button } from '#lib/components/ui/button/index.js';
	import * as Empty from '#lib/components/ui/empty/index.js';
</script>

<svelte:head><title>{page.status} · Online Judge</title></svelte:head>

<Empty.Root class="border">
	<Empty.Header>
		<Empty.Title>{page.status === 404 ? 'Not found' : `Error ${page.status}`}</Empty.Title>
		<Empty.Description data-testid="error-message">{page.error?.message}</Empty.Description>
	</Empty.Header>
	<Empty.Content>
		<Button href={resolve('/')} variant="outline">Back to problems</Button>
	</Empty.Content>
</Empty.Root>

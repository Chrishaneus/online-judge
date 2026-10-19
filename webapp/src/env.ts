import { defineEnvVars } from '@sveltejs/kit/env';

export const variables = defineEnvVars({
	API_URL: {
		description: 'Base URL of the api HTTP API, including /api/v1 (server-side only).',
		schema: (value) => value || 'http://127.0.0.1:8000/api/v1'
	}
});

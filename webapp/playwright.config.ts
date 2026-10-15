import { defineConfig } from '@playwright/test';

// Two modes:
// - E2E_BASE_URL set: test a running stack, e.g. `make up` at the repo root, then
//     E2E_BASE_URL=http://localhost:8080 E2E_ADMIN_TOKEN=<ADMIN_TOKEN from ../.env> npx playwright test
// - unset: start the in-memory mock rest (e2e/mock-api.ts) and a production build of the
//   webapp (`vite preview`) pointed at it. Judging is faked there; see the mock's header.
const externalBaseURL = process.env.E2E_BASE_URL;
const MOCK_PORT = 8099;
const MOCK_ADMIN_TOKEN = 'e2e-admin-token';

if (!externalBaseURL) process.env.E2E_ADMIN_TOKEN ??= MOCK_ADMIN_TOKEN;

export default defineConfig({
	testDir: 'e2e',
	testMatch: '**/*.e2e.{ts,js}',
	// Judging takes a few seconds on the real stack.
	timeout: 90_000,
	expect: { timeout: 10_000 },
	reporter: process.env.CI ? 'line' : [['list'], ['html', { open: 'never' }]],
	use: { baseURL: externalBaseURL ?? 'http://localhost:4173', trace: 'retain-on-failure' },
	webServer: externalBaseURL
		? undefined
		: [
				{
					command: 'node e2e/mock-api.ts',
					url: `http://127.0.0.1:${MOCK_PORT}/api/v1/status`,
					env: { PORT: String(MOCK_PORT), ADMIN_TOKEN: MOCK_ADMIN_TOKEN },
					reuseExistingServer: false
				},
				{
					command: 'npm run build && npm run preview -- --port 4173 --strictPort',
					port: 4173,
					env: { API_URL: `http://127.0.0.1:${MOCK_PORT}/api/v1` },
					timeout: 180_000,
					reuseExistingServer: !process.env.CI
				}
			]
});

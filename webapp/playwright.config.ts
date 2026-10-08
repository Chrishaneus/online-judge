import { defineConfig } from '@playwright/test';

// E2E tests run against the full stack: `make up` in oj-deploy, then
//   E2E_BASE_URL=http://localhost:8080 npx playwright test
// Admin flows additionally need E2E_ADMIN_TOKEN (ADMIN_TOKEN from oj-deploy/.env).
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:8080';

export default defineConfig({
	testDir: 'e2e',
	testMatch: '**/*.e2e.{ts,js}',
	reporter: process.env.CI ? 'line' : [['list'], ['html', { open: 'never' }]],
	use: { baseURL, trace: 'retain-on-failure' }
});

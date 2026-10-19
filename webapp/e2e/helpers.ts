import { expect, type Page } from '@playwright/test';

export const PYTHON = '1'; // Language.PYTHON as posted by the language <select>

export const AC_SOURCE = 'a, b = map(int, input().split())\nprint(a + b)\n';
export const WA_SOURCE = 'a, b = map(int, input().split())\nprint(a - b)\n';

/** Open the seeded A + B problem from the problem list. */
export async function openAPlusB(page: Page): Promise<void> {
	await page.goto('/');
	await page.getByRole('link', { name: 'A + B', exact: true }).click();
	await expect(page.getByRole('heading', { level: 1, name: 'A + B' })).toBeVisible();
}

export async function writeSolution(
	page: Page,
	source: string,
	username = 'e2e-user'
): Promise<void> {
	await page.getByLabel('Language').selectOption(PYTHON);
	await page.getByLabel('Your name').fill(username);
	await page.getByRole('textbox', { name: 'Source code' }).fill(source);
}

export function adminToken(): string {
	const token = process.env.E2E_ADMIN_TOKEN;
	if (!token)
		throw new Error('Set E2E_ADMIN_TOKEN (ADMIN_TOKEN of the api) to run the admin specs.');
	return token;
}

export async function adminSignIn(page: Page, token = adminToken()): Promise<void> {
	await page.goto('/admin');
	await expect(page).toHaveURL(/\/admin\/login/);
	await page.getByLabel('Admin token').fill(token);
	await page.getByRole('button', { name: 'Sign in' }).click();
	await expect(page.getByRole('heading', { name: 'Problems' })).toBeVisible();
}

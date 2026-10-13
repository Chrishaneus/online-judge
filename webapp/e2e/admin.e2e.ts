import { expect, test } from '@playwright/test';
import { adminSignIn } from './helpers.js';

test('admin pages require a valid token', async ({ page }) => {
	await page.goto('/admin/problems/new');
	await expect(page).toHaveURL(/\/admin\/login\?redirectTo=/);
	await page.getByLabel('Admin token').fill('definitely-wrong');
	await page.getByRole('button', { name: 'Sign in' }).click();
	await expect(page.getByTestId('login-error')).toHaveText(/Invalid admin token/);
});

test('admin creates a problem, manages its test cases and deletes it', async ({ page }) => {
	const slug = `e2e-${Date.now()}`;
	const title = `E2E Echo ${Date.now()}`;
	page.on('dialog', (d) => d.accept());

	await adminSignIn(page);
	await page.getByRole('link', { name: 'New problem' }).first().click();

	await page.getByLabel('Slug').fill(slug);
	await page.getByLabel('Title').fill(title);
	await page.getByLabel('Difficulty').selectOption({ label: 'Medium' });
	await page.getByLabel('Statement (Markdown)').fill('Print the **input** back.');
	const rows = page.getByTestId('test-case-row');
	await rows.nth(0).getByLabel('Input').fill('hello');
	await rows.nth(0).getByLabel('Expected output').fill('hello');
	await rows.nth(1).getByLabel('Input').fill('world');
	await rows.nth(1).getByLabel('Expected output').fill('world');
	await page.getByRole('button', { name: 'Add test case' }).click();
	await expect(rows).toHaveCount(3);
	await rows
		.nth(2)
		.getByRole('button', { name: /Remove/ })
		.click();
	await expect(rows).toHaveCount(2);
	await page.getByRole('button', { name: 'Create problem' }).click();

	// Test case page of the new problem.
	await expect(page).toHaveURL(/\/admin\/problems\/\d+/);
	await expect(page.getByRole('heading', { name: title })).toBeVisible();
	const cases = page.getByTestId('test-cases').getByRole('listitem');
	await expect(cases).toHaveCount(2);
	await expect(cases.first().getByText('sample')).toBeVisible();

	await page.getByLabel('Input', { exact: true }).fill('third');
	await page.getByLabel('Expected output', { exact: true }).fill('third');
	await page.getByRole('button', { name: 'Add test case' }).click();
	await expect(cases).toHaveCount(3);

	await page.getByRole('button', { name: 'Delete test case 3' }).click();
	await expect(cases).toHaveCount(2);

	// Public pages show it.
	await page.goto('/');
	await expect(page.getByRole('link', { name: title })).toBeVisible();

	// Delete it.
	await page.goto('/admin');
	await page.getByRole('button', { name: `Delete ${title}` }).click();
	await expect(page.getByRole('cell', { name: title })).toHaveCount(0);
	await page.goto('/');
	await expect(page.getByRole('link', { name: title })).toHaveCount(0);

	// Sign out.
	await page.goto('/admin');
	await page.getByRole('button', { name: 'Sign out' }).click();
	await expect(page).toHaveURL(/\/admin\/login/);
	await page.goto('/admin');
	await expect(page).toHaveURL(/\/admin\/login/);
});

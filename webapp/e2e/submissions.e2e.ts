import { expect, test } from '@playwright/test';
import { AC_SOURCE, openAPlusB, writeSolution } from './helpers.js';

test('filters submissions by user', async ({ page }) => {
	const user = `filter-${Date.now()}`;
	await openAPlusB(page);
	await writeSolution(page, AC_SOURCE, user);
	await page.getByRole('button', { name: 'Submit' }).click();
	await expect(page).toHaveURL(/\/submissions\/\d+$/);

	await page.getByRole('link', { name: 'Submissions', exact: true }).first().click();
	await page.getByLabel('User').fill(user);
	await page.getByRole('button', { name: 'Filter' }).click();

	await expect(page).toHaveURL(new RegExp(`user=${user}`));
	const rows = page.getByTestId('submissions').getByRole('row');
	await expect(rows).toHaveCount(2); // header + our submission
	await expect(rows.nth(1)).toContainText(user);
	await expect(rows.nth(1).getByTestId('verdict')).toHaveText('Accepted', { timeout: 60_000 });

	await page.getByLabel('User').fill(`${user}-nobody`);
	await page.getByRole('button', { name: 'Filter' }).click();
	await expect(page.getByText('No submissions found')).toBeVisible();
});

test('switches between light and dark mode', async ({ page }) => {
	await page.goto('/');
	await page.getByRole('button', { name: 'Toggle theme' }).click();
	await page.getByRole('menuitem', { name: 'Dark' }).click();
	await expect(page.locator('html')).toHaveClass(/dark/);
	await page.getByRole('button', { name: 'Toggle theme' }).click();
	await page.getByRole('menuitem', { name: 'Light' }).click();
	await expect(page.locator('html')).not.toHaveClass(/dark/);
});

import { expect, test } from '@playwright/test';
import { AC_SOURCE, openAPlusB, WA_SOURCE, writeSolution } from './helpers.js';

test('lists problems with difficulty and limits', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByRole('heading', { name: 'Problems' })).toBeVisible();
	const row = page.getByRole('row').filter({ hasText: 'A + B' });
	await expect(row.getByText('Easy')).toBeVisible();
	await expect(row.getByText(/\d+ ms/)).toBeVisible();
	await expect(page.getByTestId('judge-status')).not.toHaveText(/Checking/);
});

test('shows the statement and samples of a problem', async ({ page }) => {
	await openAPlusB(page);
	await expect(page.locator('.markdown strong').first()).toHaveText('A');
	await expect(page.getByRole('heading', { name: 'Examples' })).toBeVisible();
	await expect(page.getByTestId('sample').first()).toContainText('1 2');
	await expect(page.getByRole('button', { name: 'Copy sample input 1' })).toBeVisible();
});

test('solves A + B in Python: Accepted', async ({ page }) => {
	await openAPlusB(page);
	await writeSolution(page, AC_SOURCE);
	await page.getByRole('button', { name: 'Submit' }).click();

	await expect(page).toHaveURL(/\/submissions\/\d+$/);
	await expect(page.getByTestId('verdict')).toHaveText('Accepted', { timeout: 60_000 });
	await expect(page.getByTestId('tests-passed')).toHaveText(/^(\d+)\/\1 tests passed$/);
	await expect(page.getByTestId('test-results').getByRole('row')).not.toHaveCount(0);
	await expect(page.getByTestId('submission-source')).toContainText('print(a + b)');
});

test('a wrong solution gets Wrong Answer', async ({ page }) => {
	await openAPlusB(page);
	await writeSolution(page, WA_SOURCE);
	await page.getByRole('button', { name: 'Submit' }).click();

	await expect(page).toHaveURL(/\/submissions\/\d+$/);
	await expect(page.getByTestId('verdict')).toHaveText('Wrong Answer', { timeout: 60_000 });
	await expect(page.getByTestId('verdict')).toHaveAttribute('data-tone', 'danger');
});

test('runs code against custom input', async ({ page }) => {
	await openAPlusB(page);
	await writeSolution(page, AC_SOURCE);
	await page.getByLabel('Custom input (for Run)').fill('20 22');
	await page.getByRole('button', { name: 'Run' }).click();

	const result = page.getByTestId('run-result');
	await expect(result).toContainText('OK', { timeout: 60_000 });
	await expect(page.getByTestId('run-stdout')).toHaveText('42');
	await expect(page).toHaveURL(/\/problems\/\d+$/);
});

test('keeps the draft and name across reloads', async ({ page }) => {
	await openAPlusB(page);
	await writeSolution(page, '# my draft\n', 'draft-keeper');
	await page.reload();
	await expect(page.getByRole('textbox', { name: 'Source code' })).toHaveValue('# my draft\n');
	await expect(page.getByLabel('Your name')).toHaveValue('draft-keeper');
});

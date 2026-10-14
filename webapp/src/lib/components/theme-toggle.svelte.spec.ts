import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import ThemeToggle from './theme-toggle.svelte';

const storedMode = () => localStorage.getItem('mode-watcher-mode');

describe('theme-toggle.svelte', () => {
	it('lets the user pick light, dark or the system theme', async () => {
		render(ThemeToggle);

		for (const [label, mode] of [
			['Dark', 'dark'],
			['Light', 'light'],
			['System', 'system']
		]) {
			await page.getByRole('button', { name: 'Toggle theme' }).click();
			await page.getByRole('menuitem', { name: label }).click();
			await expect.poll(storedMode).toBe(mode);
			await expect.element(page.getByRole('menuitem', { name: label })).not.toBeInTheDocument();
		}
	});
});

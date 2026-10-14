import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import CodeEditor from './code-editor.svelte';

function textarea(): HTMLTextAreaElement {
	return page.getByRole('textbox', { name: 'Source code' }).element() as HTMLTextAreaElement;
}

describe('code-editor.svelte', () => {
	it('is labelled and posts its value under the given name', async () => {
		render(CodeEditor, { id: 'src', name: 'source', value: 'print(1)' });
		const editor = page.getByRole('textbox', { name: 'Source code' });
		await expect.element(editor).toHaveValue('print(1)');
		await expect.element(editor).toHaveAttribute('name', 'source');
		await expect.element(editor).toHaveAccessibleDescription(/Tab indents/);
	});

	it('inserts spaces on Tab instead of leaving the field', async () => {
		const onchange = vi.fn();
		render(CodeEditor, { value: '', onchange });
		await page.getByRole('textbox', { name: 'Source code' }).click();
		await userEvent.keyboard('if x:{Enter}');
		await userEvent.keyboard('{Tab}pass');
		await expect.element(page.getByRole('textbox')).toHaveValue('if x:\n    pass');
		expect(document.activeElement).toBe(textarea());
		expect(onchange).toHaveBeenLastCalledWith('if x:\n    pass');
	});

	it('indents and dedents every selected line', async () => {
		render(CodeEditor, { value: 'a\nb' });
		const ta = textarea();
		ta.focus();
		ta.setSelectionRange(0, ta.value.length);
		await userEvent.keyboard('{Tab}');
		expect(ta.value).toBe('    a\n    b');
		ta.setSelectionRange(0, ta.value.length);
		await userEvent.keyboard('{Shift>}{Tab}{/Shift}');
		expect(ta.value).toBe('a\nb');
	});

	it('lets keyboard users leave with Escape then Tab', async () => {
		render(CodeEditor, { value: 'x' });
		const ta = textarea();
		ta.focus();
		await userEvent.keyboard('{Escape}{Tab}');
		expect(ta.value).toBe('x');
		expect(document.activeElement).not.toBe(ta);
	});

	it('calls the submit shortcut on Ctrl+Enter', async () => {
		const onsubmitshortcut = vi.fn();
		render(CodeEditor, { value: 'x', onsubmitshortcut });
		textarea().focus();
		await userEvent.keyboard('{Control>}{Enter}{/Control}');
		expect(onsubmitshortcut).toHaveBeenCalledOnce();
		expect(textarea().value).toBe('x');
	});
});

import { describe, expect, it } from 'vitest';
import { escapeHtml, renderInline, renderMarkdown } from './markdown.js';

/** Every tag the renderer may emit; anything else in the output means an injection. */
const ALLOWED = /^<\/?(p|h[1-6]|strong|em|code|pre|ul|ol|li)>$/;
const tags = (html: string) => html.match(/<[^>]*>/g) ?? [];

describe('markdown escaping', () => {
	it('escapes all HTML special characters', () => {
		expect(escapeHtml(`<a href="x">'&'</a>`)).toBe(
			'&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;'
		);
	});

	it.each([
		'<script>alert(1)</script>',
		'### <img src=x onerror=alert(1)>',
		'<a href="javascript:alert(1)">x</a>',
		'**<svg onload=alert(1)>**',
		'*<iframe src=//evil>*',
		'- <style>body{display:none}</style>',
		'`</code><script>alert(1)</script>`',
		'```\n</code></pre><script>alert(1)</script>\n```',
		'1. "><img src=x onerror=alert(1)>',
		'<<script>script>alert(1)<</script>/script>',
		'**"onmouseover="alert(1)**'
	])('neutralises %s', (input) => {
		const out = renderMarkdown(input);
		for (const tag of tags(out)) expect(tag).toMatch(ALLOWED);
		expect(out).not.toMatch(/<(script|img|svg|iframe|style|a)\b/i);
	});

	it('keeps code spans literal', () => {
		expect(renderMarkdown('`<b>`')).toBe('<p><code>&lt;b&gt;</code></p>');
	});
});

describe('markdown rendering', () => {
	it('renders inline formatting', () => {
		expect(renderInline('**A** and *b* `c*d*`')).toBe(
			'<strong>A</strong> and <em>b</em> <code>c*d*</code>'
		);
		expect(renderInline('a ` b')).toBe('a ` b');
	});

	it('renders headings, paragraphs, lists and code blocks', () => {
		const md = [
			'Intro line one',
			'continues here.',
			'',
			'### Input',
			'- first',
			'- second',
			'',
			'1. one',
			'2. two',
			'',
			'```',
			'x < y',
			'```'
		].join('\n');
		expect(renderMarkdown(md)).toBe(
			[
				'<p>Intro line one continues here.</p>',
				'<h3>Input</h3>',
				'<ul><li>first</li><li>second</li></ul>',
				'<ol><li>one</li><li>two</li></ol>',
				'<pre><code>x &lt; y</code></pre>'
			].join('\n')
		);
	});

	it('handles empty and CRLF input', () => {
		expect(renderMarkdown('')).toBe('');
		expect(renderMarkdown(null)).toBe('');
		expect(renderMarkdown(undefined)).toBe('');
		expect(renderMarkdown('a\r\nb')).toBe('<p>a b</p>');
	});

	it('renders the seeded A + B statement', () => {
		const out = renderMarkdown(
			'Read two integers **A** and **B**.\n\n### Input\nA line with `A` and `B` (`-10^9 <= A, B <= 10^9`).'
		);
		expect(out).toContain('<strong>A</strong>');
		expect(out).toContain('<h3>Input</h3>');
		expect(out).toContain('<code>-10^9 &lt;= A, B &lt;= 10^9</code>');
	});
});

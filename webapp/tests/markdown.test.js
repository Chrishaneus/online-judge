import assert from 'node:assert/strict';
import { test } from 'node:test';

import { escapeHtml, renderInline, renderMarkdown } from '../public/js/markdown.js';

test('escapes HTML everywhere', () => {
  assert.equal(escapeHtml(`<a href="x">'&'</a>`), '&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;');
  const out = renderMarkdown('<script>alert(1)</script>\n\n### <img src=x onerror=alert(1)>\n\n`<b>`');
  assert.ok(!out.includes('<script>'));
  assert.ok(!out.includes('<img'));
  assert.ok(out.includes('<code>&lt;b&gt;</code>'));
});

test('inline formatting', () => {
  assert.equal(renderInline('**A** and *b* `c*d*`'), '<strong>A</strong> and <em>b</em> <code>c*d*</code>');
  assert.equal(renderInline('a ` b'), 'a ` b');
});

test('headings, paragraphs, lists and code blocks', () => {
  const md = [
    'Intro line one',
    'continues here.',
    '',
    '### Input',
    '- first',
    '- second',
    '',
    '```',
    'x < y',
    '```',
  ].join('\n');
  assert.equal(
    renderMarkdown(md),
    [
      '<p>Intro line one continues here.</p>',
      '<h3>Input</h3>',
      '<ul><li>first</li><li>second</li></ul>',
      '<pre><code>x &lt; y</code></pre>',
    ].join('\n'),
  );
});

test('handles empty and CRLF input', () => {
  assert.equal(renderMarkdown(''), '');
  assert.equal(renderMarkdown(null), '');
  assert.equal(renderMarkdown('a\r\nb'), '<p>a b</p>');
});

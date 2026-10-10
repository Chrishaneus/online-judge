/**
 * Minimal, escape-first Markdown renderer for problem statements.
 *
 * Every piece of source text is HTML-escaped *before* any markup is added, and the
 * only markup ever emitted is a fixed set of attribute-less tags, so the output is
 * safe for `{@html}` even when the statement is untrusted.
 *
 * Supported: #-headings, paragraphs, **bold**, *italic*, `code`, fenced ``` code
 * blocks, - / * bullet lists and 1. numbered lists.
 */

const ESCAPES: Record<string, string> = {
	'&': '&amp;',
	'<': '&lt;',
	'>': '&gt;',
	'"': '&quot;',
	"'": '&#39;'
};

export function escapeHtml(s: string): string {
	return String(s).replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

function emphasis(escaped: string): string {
	return escaped
		.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
		.replace(/\*(.+?)\*/g, '<em>$1</em>');
}

export function renderInline(text: string): string {
	const parts = String(text).split('`');
	// An unmatched trailing backtick is literal text, not an open code span.
	if (parts.length % 2 === 0) {
		const last = parts.pop();
		parts[parts.length - 1] += '`' + last;
	}
	return parts
		.map((part, i) =>
			i % 2 === 1 ? `<code>${escapeHtml(part)}</code>` : emphasis(escapeHtml(part))
		)
		.join('');
}

export function renderMarkdown(src: string | null | undefined): string {
	const lines = String(src ?? '')
		.replace(/\r\n?/g, '\n')
		.split('\n');
	const out: string[] = [];
	let para: string[] = [];
	let list: string[] = [];
	let listTag: 'ul' | 'ol' = 'ul';

	const flushPara = () => {
		if (para.length) out.push(`<p>${renderInline(para.join(' '))}</p>`);
		para = [];
	};
	const flushList = () => {
		if (list.length) {
			out.push(
				`<${listTag}>${list.map((li) => `<li>${renderInline(li)}</li>`).join('')}</${listTag}>`
			);
		}
		list = [];
	};
	const pushItem = (tag: 'ul' | 'ol', text: string) => {
		flushPara();
		if (list.length && listTag !== tag) flushList();
		listTag = tag;
		list.push(text);
	};

	for (let i = 0; i < lines.length; i++) {
		const line = lines[i];

		if (line.trimStart().startsWith('```')) {
			flushPara();
			flushList();
			const code: string[] = [];
			i++;
			while (i < lines.length && !lines[i].trimStart().startsWith('```')) code.push(lines[i++]);
			out.push(`<pre><code>${escapeHtml(code.join('\n'))}</code></pre>`);
			continue;
		}

		const heading = /^(#{1,6})\s+(.*)$/.exec(line);
		if (heading) {
			flushPara();
			flushList();
			const n = heading[1].length;
			out.push(`<h${n}>${renderInline(heading[2].trim())}</h${n}>`);
			continue;
		}

		const bullet = /^\s*[-*]\s+(.*)$/.exec(line);
		if (bullet) {
			pushItem('ul', bullet[1]);
			continue;
		}

		const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
		if (numbered) {
			pushItem('ol', numbered[1]);
			continue;
		}

		if (line.trim() === '') {
			flushPara();
			flushList();
			continue;
		}

		flushList();
		para.push(line.trim());
	}
	flushPara();
	flushList();
	return out.join('\n');
}

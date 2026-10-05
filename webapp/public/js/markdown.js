// Minimal, escape-first Markdown renderer for problem statements.
//
// Every piece of source text is HTML-escaped *before* any markup is added,
// so the output is safe to assign to innerHTML even for untrusted input.
// Supported: #-headings, paragraphs, **bold**, *italic*, `code`,
// fenced ``` code blocks, and - / * bullet lists.

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

function emphasis(escaped) {
  return escaped
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>');
}

export function renderInline(text) {
  const parts = String(text).split('`');
  // An unmatched trailing backtick is literal text, not an open code span.
  if (parts.length % 2 === 0) {
    const last = parts.pop();
    parts[parts.length - 1] += '`' + last;
  }
  return parts
    .map((part, i) => (i % 2 === 1 ? `<code>${escapeHtml(part)}</code>` : emphasis(escapeHtml(part))))
    .join('');
}

export function renderMarkdown(src) {
  const lines = String(src ?? '').replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  let para = [];
  let list = [];

  const flushPara = () => {
    if (para.length) out.push(`<p>${renderInline(para.join(' '))}</p>`);
    para = [];
  };
  const flushList = () => {
    if (list.length) out.push(`<ul>${list.map((li) => `<li>${renderInline(li)}</li>`).join('')}</ul>`);
    list = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.trimStart().startsWith('```')) {
      flushPara();
      flushList();
      const code = [];
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
      flushPara();
      list.push(bullet[1]);
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

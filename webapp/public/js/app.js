import { api, getAdminToken, setAdminToken } from './api.js';
import { h, mount, timeAgo } from './dom.js';
import { renderMarkdown } from './markdown.js';

const app = document.getElementById('app');
const FINAL = new Set(['FINISHED', 'FAILED']);
const VERDICT_NAMES = {
  AC: 'Accepted', WA: 'Wrong Answer', TLE: 'Time Limit Exceeded', MLE: 'Memory Limit Exceeded',
  OLE: 'Output Limit Exceeded', RE: 'Runtime Error', CE: 'Compilation Error', IE: 'Internal Error',
  OK: 'OK', PENDING: 'Pending', JUDGING: 'Judging',
};

const TEMPLATES = {
  python: 'import sys\n\n\ndef main():\n    data = sys.stdin.read().split()\n    \n\n\nmain()\n',
  cpp: '#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n    \n    return 0;\n}\n',
  c: '#include <stdio.h>\n\nint main(void) {\n    \n    return 0;\n}\n',
  javascript: "const input = require('fs').readFileSync(0, 'utf8');\nconst lines = input.trim().split('\\n');\n\n",
};

// ---------- small utilities ----------

const store = {
  get(key, fallback = '') {
    try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, value); } catch { /* ignore */ }
  },
};

let toastTimer;
function toast(message, isError = false) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.className = `show${isError ? ' error' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ''; }, isError ? 6000 : 3000);
}

function username() {
  return document.getElementById('username').value.trim() || 'anonymous';
}

function verdictBadge(sub) {
  const key = FINAL.has(sub.status) ? sub.verdict || sub.status : sub.status;
  return h('span', { class: `badge v-${key}`, title: VERDICT_NAMES[key] || key }, key);
}

function difficultyBadge(d) {
  return h('span', { class: `badge d-${d}` }, d);
}

function langName(languages, id) {
  return languages.find((l) => l.id === id)?.name ?? id;
}

let languagesCache;
async function languages() {
  languagesCache ??= api.languages().catch((e) => { languagesCache = undefined; throw e; });
  return languagesCache;
}

function errorView(err) {
  return h('div', { class: 'card error' }, h('strong', {}, 'Error: '), err.message || String(err));
}

/** Poll a submission until it is judged. Stops when the route changes. */
async function pollSubmission(id, token, onUpdate) {
  const deadline = Date.now() + 3 * 60_000;
  let delay = 500;
  while (token === routeToken && Date.now() < deadline) {
    const sub = await api.submission(id);
    if (token !== routeToken) return;
    onUpdate(sub);
    if (FINAL.has(sub.status)) return sub;
    await new Promise((r) => setTimeout(r, delay));
    delay = Math.min(delay * 1.4, 2500);
  }
}

function testChips(results) {
  return h('div', { class: 'tests' },
    results.map((t) => h('div', { class: `test-chip v-${t.verdict}`, title: VERDICT_NAMES[t.verdict] },
      h('strong', {}, t.verdict),
      `#${t.test}${t.sample ? ' (sample)' : ''}`,
      h('div', { class: 'muted' }, `${t.time_ms} ms · ${Math.round((t.memory_kb || 0) / 1024)} MB`))));
}

function submissionSummary(sub) {
  const parts = [verdictBadge(sub)];
  if (FINAL.has(sub.status)) {
    parts.push(h('span', {}, `${sub.passed}/${sub.total} tests`));
    if (sub.time_ms) parts.push(h('span', { class: 'muted' }, `${sub.time_ms} ms`));
  }
  parts.push(h('span', { class: 'spacer' }));
  parts.push(h('a', { href: `#/submissions/${sub.id}` }, `#${sub.id}`));
  return h('div', { class: 'head' }, parts);
}

// ---------- views ----------

async function problemsView() {
  const problems = await api.problems();
  return [
    h('div', { class: 'row' }, h('h1', {}, 'Problems'), h('span', { class: 'spacer' }),
      h('span', { class: 'muted' }, `${problems.length} problem${problems.length === 1 ? '' : 's'}`)),
    h('p', { class: 'muted' }, 'Pick a problem, write a solution, and submit it for judging.'),
    problems.length === 0
      ? h('div', { class: 'card empty' }, 'No problems yet. An admin can add some on the Admin page.')
      : h('table', {},
        h('thead', {}, h('tr', {}, h('th', { class: 'num' }, '#'), h('th', {}, 'Title'), h('th', {}, 'Difficulty'),
          h('th', { class: 'num' }, 'Time limit'), h('th', { class: 'num' }, 'Memory'), h('th', {}, ''))),
        h('tbody', {}, problems.map((p) => h('tr', {},
          h('td', { class: 'num' }, p.id),
          h('td', {}, h('a', { href: `#/problems/${p.id}` }, p.title)),
          h('td', {}, difficultyBadge(p.difficulty)),
          h('td', { class: 'num' }, `${p.time_limit_ms} ms`),
          h('td', { class: 'num' }, `${p.memory_limit_mb} MB`),
          h('td', {}, h('a', { href: `#/submissions?problem=${p.id}`, class: 'muted' }, 'submissions')))))),
  ];
}

function copyButton(text) {
  return h('button', {
    class: 'link',
    type: 'button',
    onclick: () => navigator.clipboard?.writeText(text).then(() => toast('Copied'), () => {}),
  }, 'copy');
}

async function problemView(id, token) {
  const [problem, langs] = await Promise.all([api.problem(id), languages()]);

  const langSelect = h('select', { 'aria-label': 'Language' },
    langs.map((l) => h('option', { value: l.id }, l.name)));
  langSelect.value = store.get('oj.lang', langs[0]?.id) || langs[0]?.id;
  if (!langs.some((l) => l.id === langSelect.value)) langSelect.value = langs[0]?.id;

  const draftKey = () => `oj.draft.${problem.id}.${langSelect.value}`;
  const editor = h('textarea', { class: 'code editor', spellcheck: false, 'aria-label': 'Source code' });
  const loadDraft = () => { editor.value = store.get(draftKey(), TEMPLATES[langSelect.value] ?? ''); };
  loadDraft();

  editor.addEventListener('input', () => store.set(draftKey(), editor.value));
  editor.addEventListener('keydown', (e) => {
    if (e.key === 'Tab' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      editor.setRangeText('    ', editor.selectionStart, editor.selectionEnd, 'end');
      store.set(draftKey(), editor.value);
    } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      submitBtn.click();
    }
  });
  langSelect.addEventListener('change', () => { store.set('oj.lang', langSelect.value); loadDraft(); });

  const stdin = h('textarea', { class: 'code', rows: 4, spellcheck: false, 'aria-label': 'Custom input' });
  stdin.value = problem.samples[0]?.input ?? '';
  const output = h('div', { class: 'result-panel' });

  const runBtn = h('button', { type: 'button' }, 'Run');
  const submitBtn = h('button', { type: 'button', class: 'primary', title: 'Ctrl+Enter' }, 'Submit');

  runBtn.addEventListener('click', async () => {
    runBtn.disabled = true;
    mount(output, h('p', { class: 'muted' }, 'Running…'));
    try {
      const r = await api.run({ language: langSelect.value, source: editor.value, stdin: stdin.value, problem_id: problem.id });
      if (token !== routeToken) return;
      const sections = [h('div', { class: 'head' }, h('span', { class: `badge v-${r.status}` }, r.status),
        r.status !== 'CE' ? h('span', { class: 'muted' }, `${r.time_ms} ms · ${Math.round(r.memory_kb / 1024)} MB · exit ${r.exit_code}`) : null)];
      if (r.status === 'CE') sections.push(h('pre', {}, r.compile_output));
      else {
        sections.push(h('div', { class: 'muted' }, 'stdout'), h('pre', {}, r.stdout || ' '));
        if (r.stderr) sections.push(h('div', { class: 'muted' }, 'stderr'), h('pre', { class: 'error' }, r.stderr));
      }
      mount(output, sections);
    } catch (err) {
      mount(output, errorView(err));
    } finally {
      runBtn.disabled = false;
    }
  });

  submitBtn.addEventListener('click', async () => {
    submitBtn.disabled = true;
    try {
      const sub = await api.submit({ problem_id: problem.id, language: langSelect.value, source: editor.value, username: username() });
      const render = (s) => mount(output,
        h('div', { class: 'card' }, submissionSummary(s),
          s.message && FINAL.has(s.status) ? h(s.verdict === 'CE' ? 'pre' : 'p', { class: 'muted' }, s.message) : null,
          s.results?.length ? testChips(s.results) : null));
      render(sub);
      const final = await pollSubmission(sub.id, token, render);
      if (final) toast(`${VERDICT_NAMES[final.verdict] ?? final.verdict}: ${final.passed}/${final.total}`, final.verdict !== 'AC');
    } catch (err) {
      mount(output, errorView(err));
    } finally {
      submitBtn.disabled = false;
    }
  });

  const samples = problem.samples.map((s, i) => h('div', { class: 'sample' },
    h('div', {}, h('div', { class: 'label' }, `Sample input ${i + 1}`,
      h('span', {}, h('button', { class: 'link', type: 'button', onclick: () => { stdin.value = s.input; } }, 'use'), ' · ', copyButton(s.input))),
    h('pre', {}, s.input)),
    h('div', {}, h('div', { class: 'label' }, `Sample output ${i + 1}`, copyButton(s.output)), h('pre', {}, s.output))));

  return h('div', { class: 'split' },
    h('section', { class: 'card' },
      h('div', { class: 'row' }, h('h1', {}, problem.title), difficultyBadge(problem.difficulty)),
      h('div', { class: 'limits' },
        h('span', {}, `⏱ ${problem.time_limit_ms} ms`),
        h('span', {}, `▣ ${problem.memory_limit_mb} MB`),
        h('a', { href: `#/submissions?problem=${problem.id}` }, 'submissions')),
      h('div', { class: 'statement', html: renderMarkdown(problem.statement) }),
      samples.length ? h('h2', {}, 'Examples') : null,
      samples),
    h('section', { class: 'card sticky' },
      h('div', { class: 'row' }, langSelect,
        h('button', { type: 'button', class: 'link', onclick: () => {
          if (confirm('Replace your code with the starter template?')) {
            editor.value = TEMPLATES[langSelect.value] ?? '';
            store.set(draftKey(), editor.value);
          }
        } }, 'reset'),
        h('span', { class: 'spacer' }), runBtn, submitBtn),
      h('div', { style: 'margin-top:10px' }, editor),
      h('label', { class: 'field', style: 'margin-top:10px' }, 'Custom input (for Run)', stdin),
      output));
}

async function submissionsView(params, token) {
  const problemId = params.get('problem') || '';
  const user = params.get('user') ?? '';
  const [subs, langs] = await Promise.all([
    api.submissions({ problem_id: problemId, username: user, limit: 50 }),
    languages().catch(() => []),
  ]);

  const userInput = h('input', { value: user, placeholder: 'any user', maxlength: 32 });
  const problemInput = h('input', { value: problemId, placeholder: 'any', type: 'number', min: 1, style: 'width:90px' });
  const applyFilter = (e) => {
    e?.preventDefault();
    const q = new URLSearchParams();
    if (userInput.value.trim()) q.set('user', userInput.value.trim());
    if (problemInput.value) q.set('problem', problemInput.value);
    location.hash = `#/submissions${q.toString() ? `?${q}` : ''}`;
  };

  const tbody = h('tbody', {});
  const renderRows = (list) => mount(tbody, list.map((s) => h('tr', {},
    h('td', { class: 'num' }, h('a', { href: `#/submissions/${s.id}` }, s.id)),
    h('td', {}, h('a', { href: `#/problems/${s.problem_id}` }, s.problem_id)),
    h('td', {}, s.username),
    h('td', {}, langName(langs, s.language)),
    h('td', {}, verdictBadge(s)),
    h('td', { class: 'num' }, FINAL.has(s.status) ? `${s.passed}/${s.total}` : '–'),
    h('td', { class: 'num' }, FINAL.has(s.status) ? `${s.time_ms} ms` : '–'),
    h('td', { class: 'muted', title: new Date(s.created_at).toLocaleString() }, timeAgo(s.created_at)))));
  renderRows(subs);

  // Keep refreshing while anything is still being judged.
  (async () => {
    let list = subs;
    while (token === routeToken && list.some((s) => !FINAL.has(s.status))) {
      await new Promise((r) => setTimeout(r, 1500));
      if (token !== routeToken) return;
      try {
        list = await api.submissions({ problem_id: problemId, username: user, limit: 50 });
        if (token === routeToken) renderRows(list);
      } catch { return; }
    }
  })();

  return [
    h('h1', {}, 'Submissions'),
    h('form', { class: 'row', style: 'margin:12px 0', onsubmit: applyFilter },
      h('label', { class: 'handle' }, 'User', userInput),
      h('label', { class: 'handle' }, 'Problem', problemInput),
      h('button', { type: 'submit' }, 'Filter'),
      h('button', { type: 'button', class: 'link', onclick: () => { userInput.value = username(); applyFilter(); } }, 'mine')),
    subs.length === 0
      ? h('div', { class: 'card empty' }, 'No submissions found.')
      : h('table', {},
        h('thead', {}, h('tr', {}, ['#', 'Problem', 'User', 'Language', 'Verdict', 'Tests', 'Time', 'When']
          .map((t, i) => h('th', { class: [0, 5, 6].includes(i) ? 'num' : '' }, t)))),
        tbody),
  ];
}

async function submissionView(id, token) {
  const [sub, langs] = await Promise.all([api.submission(id), languages().catch(() => [])]);
  const body = h('div', {});
  const render = (s) => mount(body,
    h('div', { class: 'card' },
      submissionSummary(s),
      h('div', { class: 'muted' },
        `Problem `, h('a', { href: `#/problems/${s.problem_id}` }, `#${s.problem_id}`),
        ` · ${s.username} · ${langName(langs, s.language)} · ${new Date(s.created_at).toLocaleString()}`),
      s.message ? h(s.verdict === 'CE' ? 'pre' : 'p', { style: 'margin-top:10px' }, s.message) : null,
      s.results?.length ? testChips(s.results) : null),
    h('h2', {}, 'Source'),
    h('pre', {}, h('code', {}, s.source)));
  render(sub);
  if (!FINAL.has(sub.status)) pollSubmission(sub.id, token, render).catch(() => {});
  return [h('h1', {}, `Submission #${sub.id}`), body];
}

function testCaseRow(container, tc = { input: '', expected_output: '', is_sample: false }) {
  const input = h('textarea', { class: 'code', rows: 3, placeholder: 'input' });
  const expected = h('textarea', { class: 'code', rows: 3, placeholder: 'expected output' });
  const sample = h('input', { type: 'checkbox' });
  input.value = tc.input;
  expected.value = tc.expected_output;
  sample.checked = tc.is_sample;
  const row = h('div', { class: 'tc-row' },
    h('label', { class: 'field' }, 'Input', input),
    h('label', { class: 'field' }, 'Expected output', expected),
    h('div', { class: 'actions' },
      h('label', { class: 'handle' }, sample, 'sample'),
      h('button', { type: 'button', class: 'danger', onclick: () => row.remove() }, 'Remove')));
  row.read = () => ({ input: input.value, expected_output: expected.value, is_sample: sample.checked });
  container.append(row);
}

async function adminView() {
  const tokenInput = h('input', { type: 'password', placeholder: 'admin token', value: getAdminToken(), autocomplete: 'off', style: 'min-width:260px' });
  const status = h('span', { class: 'muted' });
  const verify = async () => {
    setAdminToken(tokenInput.value.trim());
    try {
      await api.admin.verify();
      status.textContent = '✓ authenticated';
      status.className = 'v-AC';
    } catch (err) {
      status.textContent = err.message;
      status.className = 'error';
    }
  };

  // Create problem form.
  const f = {
    slug: h('input', { required: true, pattern: '[a-z0-9]+(-[a-z0-9]+)*', placeholder: 'two-sum' }),
    title: h('input', { required: true, maxlength: 200, placeholder: 'Two Sum' }),
    difficulty: h('select', {}, ['easy', 'medium', 'hard'].map((d) => h('option', { value: d }, d))),
    time: h('input', { type: 'number', min: 100, max: 15000, value: 1000 }),
    memory: h('input', { type: 'number', min: 16, max: 1024, value: 256 }),
    statement: h('textarea', { rows: 10, placeholder: 'Markdown statement. Use ### Input / ### Output sections.' }),
  };
  const tcs = h('div', {});
  testCaseRow(tcs, { input: '', expected_output: '', is_sample: true });
  testCaseRow(tcs);

  const listBox = h('div', {});
  const refreshList = async () => {
    const problems = await api.problems();
    mount(listBox, problems.length === 0 ? h('p', { class: 'muted' }, 'No problems.') : h('table', {},
      h('thead', {}, h('tr', {}, h('th', {}, '#'), h('th', {}, 'Slug'), h('th', {}, 'Title'), h('th', {}, ''))),
      h('tbody', {}, problems.map((p) => h('tr', {},
        h('td', {}, p.id), h('td', {}, p.slug), h('td', {}, h('a', { href: `#/problems/${p.id}` }, p.title)),
        h('td', {}, h('button', { type: 'button', class: 'danger', onclick: async () => {
          if (!confirm(`Delete "${p.title}" and all its submissions?`)) return;
          try { await api.admin.deleteProblem(p.id); toast('Deleted'); refreshList(); } catch (err) { toast(err.message, true); }
        } }, 'Delete')))))));
  };
  await refreshList();

  const form = h('form', { class: 'card', onsubmit: async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button[type=submit]');
    btn.disabled = true;
    try {
      const created = await api.admin.createProblem({
        slug: f.slug.value.trim(), title: f.title.value.trim(), difficulty: f.difficulty.value,
        time_limit_ms: Number(f.time.value), memory_limit_mb: Number(f.memory.value),
        statement: f.statement.value,
        test_cases: [...tcs.children].map((r) => r.read()),
      });
      toast(`Created problem #${created.id}`);
      form.reset();
      mount(tcs);
      testCaseRow(tcs, { input: '', expected_output: '', is_sample: true });
      refreshList();
    } catch (err) {
      toast(err.message, true);
    } finally {
      btn.disabled = false;
    }
  } },
  h('h2', { style: 'margin-top:0' }, 'New problem'),
  h('div', { class: 'grid-form' },
    h('label', { class: 'field' }, 'Slug', f.slug),
    h('label', { class: 'field' }, 'Title', f.title),
    h('label', { class: 'field' }, 'Difficulty', f.difficulty),
    h('label', { class: 'field' }, 'Time limit (ms)', f.time),
    h('label', { class: 'field' }, 'Memory (MB)', f.memory)),
  h('label', { class: 'field', style: 'margin-top:12px' }, 'Statement (Markdown)', f.statement),
  h('h3', {}, 'Test cases'),
  tcs,
  h('div', { class: 'row' },
    h('button', { type: 'button', onclick: () => testCaseRow(tcs) }, '+ Add test case'),
    h('span', { class: 'spacer' }),
    h('button', { type: 'submit', class: 'primary' }, 'Create problem')));

  if (getAdminToken()) verify();
  return [
    h('h1', {}, 'Admin'),
    h('div', { class: 'card row', style: 'margin:12px 0' },
      tokenInput,
      h('button', { type: 'button', onclick: verify }, 'Use token'),
      h('button', { type: 'button', class: 'link', onclick: () => { tokenInput.value = ''; setAdminToken(''); status.textContent = 'signed out'; status.className = 'muted'; } }, 'sign out'),
      status),
    form,
    h('h2', {}, 'Existing problems'),
    listBox,
  ];
}

// ---------- router ----------

let routeToken = 0;

const routes = [
  [/^\/?$/, 'problems', () => problemsView()],
  [/^\/problems\/(\d+)$/, 'problems', (m, _q, t) => problemView(m[1], t)],
  [/^\/submissions$/, 'submissions', (_m, q, t) => submissionsView(q, t)],
  [/^\/submissions\/(\d+)$/, 'submissions', (m, _q, t) => submissionView(m[1], t)],
  [/^\/admin$/, 'admin', () => adminView()],
];

async function router() {
  const token = ++routeToken;
  const raw = location.hash.replace(/^#/, '') || '/';
  const [path, query = ''] = raw.split('?');
  const params = new URLSearchParams(query);

  const match = routes.map(([re, nav, view]) => [re.exec(path), nav, view]).find(([m]) => m);
  document.querySelectorAll('[data-nav]').forEach((a) => a.classList.toggle('active', a.dataset.nav === match?.[1]));
  if (!match) {
    mount(app, h('div', { class: 'card empty' }, 'Page not found. ', h('a', { href: '#/' }, 'Back to problems')));
    return;
  }
  mount(app, h('p', { class: 'muted' }, 'Loading…'));
  try {
    const content = await match[2](match[0], params, token);
    if (token === routeToken) {
      mount(app, content);
      app.focus({ preventScroll: true });
    }
  } catch (err) {
    if (token === routeToken) mount(app, errorView(err));
  }
}

const userInput = document.getElementById('username');
userInput.value = store.get('oj.username');
userInput.addEventListener('input', () => {
  userInput.value = userInput.value.replace(/[^A-Za-z0-9_.-]/g, '');
  store.set('oj.username', userInput.value);
});

window.addEventListener('hashchange', router);
router();

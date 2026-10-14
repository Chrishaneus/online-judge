# AGENTS.md

Instructions for any AI coding agent working in oj-webapp, the Online Judge frontend
(SvelteKit 3 + Svelte 5 runes + Tailwind 4 + shadcn-svelte, Node adapter).

## Rules (reviewers enforce these)

- **All oj-rest calls are server-side**, through the repository in `src/lib/server/api.ts`
  (load functions, form actions, `+server.ts`). The browser never talks to oj-rest.
- **Shared types come from protobuf.** `src/lib/gen/oj/v1/*_pb.ts` is generated from
  oj-proto: never hand-edit it, and don't redeclare its types. To change a shape, edit
  `oj-proto/oj/v1/*.proto` and run `make gen` there, then commit the regenerated files here.
- Over the wire: canonical proto JSON (camelCase, enums by name, int64 as strings, which
  are `bigint` in TS). Build request bodies with `create()` + `toJson()`, parse every
  response with `fromJson(Schema, json, { ignoreUnknownFields: true })`; a mismatch is a
  502 result. Errors are `ErrorResponse`.
- Enum display goes through `#lib/labels.js` (verdict / status / difficulty / language
  labels and colours). Don't hard-code labels in components.
- Markdown from the API is untrusted: render it only via `#lib/markdown.js` (escape-first).
  No other `{@html}`.
- Imports use `#lib/...` **with explicit extensions** (`#lib/labels.js`,
  `#lib/components/ui/button/index.js`).
- Server env vars are declared in `src/env.ts` and imported from `$app/env/private`.
- `resolve()` from `$app/paths` takes route IDs (`'/admin/(guarded)/problems/[id]'`,
  `` `/submissions?user=${u}` ``).
- Admin: the httpOnly `oj_admin` cookie holds the token; `hooks.server.ts` verifies it
  (only on `/admin` paths) into `locals.adminToken`. Admin pages live under
  `src/routes/admin/(guarded)/`, guarded by its `+layout.server.ts`. **Form actions are
  not covered by layout guards**: call `requireAdmin(locals, url)` in every admin action.
- UI: compose the shadcn-svelte components in `src/lib/components/ui/`; don't edit them.
  App components live in `src/lib/components/`.
- Reference docs: `docs/ai/svelte.llms-small.txt` (Svelte 5 / SvelteKit) and
  `docs/ai/shadcn-svelte.llms.txt` (component index).

## Commands

| What                | Command                                                                                |
| ------------------- | -------------------------------------------------------------------------------------- |
| Lint + types        | `npm run lint && npm run check`                                                        |
| Unit tests          | `npm run test:unit`                                                                    |
| Component tests     | `npm run test:component` (needs `npx playwright install chromium`)                     |
| E2E vs mock oj-rest | `npx playwright test` (builds, starts `e2e/mock-api.ts` + `vite preview`)              |
| E2E vs the stack    | `E2E_BASE_URL=http://localhost:8080 E2E_ADMIN_TOKEN=<ADMIN_TOKEN> npx playwright test` |
| Build / image       | `npm run build` / `docker build -t online-judge/webapp:latest .`                       |
| Regenerate types    | `make gen` (in `../oj-proto`)                                                          |

## Test levels: put each test where it belongs

- **Unit** (`src/**/*.spec.ts`, node): pure TS, e.g. the API repository with a fake
  `fetch` (`createApi(baseUrl, fetch)`), labels, Markdown escaping, drafts, form parsing.
- **Component** (`src/**/*.svelte.spec.ts`, vitest browser / chromium): Svelte
  components in a real browser.
- **E2E** (`e2e/*.e2e.ts`, Playwright): user flows through the app. Locally against the
  mock oj-rest; for real judging, against the running stack with `E2E_BASE_URL`.

## Hard rules

- Never delete, skip or loosen a test to make it pass.
- Never commit secrets; configuration comes from env vars.
- Keep changes minimal and on-task.

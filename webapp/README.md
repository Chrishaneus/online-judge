# oj-webapp

Web frontend of the Online Judge: **SvelteKit 3 + Svelte 5 (runes) + Tailwind 4 +
shadcn-svelte**, served by Node (`adapter-node`). Every call to **oj-rest** happens
server-side (load functions and form actions); the browser only talks to this app.
Request and response shapes are the protobuf types generated from
[oj-proto](../oj-proto) (`src/lib/gen/`), exchanged as canonical proto JSON.

```
browser ──> oj-webapp (node :3000) ──server-side fetch──> oj-rest /api/v1 ──gRPC──> oj-midlayer …
```

## Features

- Problem list (difficulty, limits) and problem pages with a safe Markdown statement
  renderer and samples (copy / use as input)
- Code editor: Tab / Shift+Tab indentation, per-language starter templates, drafts
  auto-saved per problem and language (localStorage), remembered language and name
- **Run** against custom input (status, stdout, stderr, time, memory, compiler output)
  and **Submit**, then a submission page that refreshes every second until judged
  (verdict, per-test results, message / compiler output, source)
- Submissions list with user / problem filters and pagination
- Admin (token in an httpOnly, `SameSite=Strict` cookie, verified with oj-rest):
  create problems with test cases, delete problems, view / add / delete test cases
- Judge status in the header (health, runners online, queue depth), light / dark mode,
  responsive layout

## Layout

```
src/
  hooks.server.ts            admin cookie -> locals.adminToken (verified via GET /admin/verify)
  env.ts                     server env vars (API_URL)
  lib/
    gen/oj/v1/*_pb.ts        generated from oj-proto, never edit
    server/api.ts            oj-rest repository (proto JSON, fromJson validation, errors)
    server/admin.ts          admin cookie + guard helpers
    labels.ts                enum labels/colours (verdict, status, difficulty, language)
    markdown.ts              escape-first Markdown renderer
    drafts.ts                starter templates + localStorage drafts
    admin-form.ts            admin form parsing / validation
    components/              app components (+ *.svelte.spec.ts); ui/ is vendored shadcn
  routes/
    +page                    problem list
    problems/[id]            statement + editor (actions: run, submit)
    submissions[/[id]]       list / detail (live polling)
    admin/login, admin/logout
    admin/(guarded)/...      problems, problems/new, problems/[id] (test cases)
e2e/                         Playwright specs + an in-memory mock oj-rest
docs/ai/                     Svelte 5 / shadcn-svelte reference for coding agents
```

## Configuration

| Variable                       | Where     | Default                        | Description                                                                                                                                                                    |
| ------------------------------ | --------- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `API_URL`                      | runtime   | `http://127.0.0.1:8000/api/v1` | oj-rest base URL including `/api/v1` (server-side only)                                                                                                                        |
| `PORT`                         | runtime   | `3000`                         | Listen port                                                                                                                                                                    |
| `ADDRESS_HEADER` / `XFF_DEPTH` | runtime   | –                              | adapter-node: take the visitor IP from a proxy header. The IP is forwarded to oj-rest as `X-Real-IP` on submit / run (rate limiting; oj-rest needs `TRUST_PROXY_HEADERS=true`) |
| `PUBLIC_ORIGIN`                | build arg | `http://localhost:8080`        | Public URL users open; SvelteKit's CSRF check compares form posts against it                                                                                                   |

## Development

```bash
npm ci
npx playwright install chromium      # once, for component and e2e tests
API_URL=http://127.0.0.1:8000/api/v1 npm run dev

npm run lint && npm run check        # prettier + eslint, svelte-check
npm run test:unit                    # src/**/*.spec.ts (node)
npm run test:component               # src/**/*.svelte.spec.ts (vitest browser, chromium)
npx playwright test                  # e2e against the mock oj-rest + a production build
E2E_BASE_URL=http://localhost:8080 E2E_ADMIN_TOKEN=... npx playwright test   # against the stack
```

Regenerate the protobuf types with `make gen` in oj-proto (never edit `src/lib/gen/`).

## Docker

```bash
docker build -t online-judge/webapp:latest --build-arg PUBLIC_ORIGIN=http://localhost:8080 .
docker run -p 8080:3000 -e API_URL=http://rest:8000/api/v1 online-judge/webapp:latest
```

The image runs `node build` as the unprivileged `node` user on port 3000, with a
healthcheck on `/`.

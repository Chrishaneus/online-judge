# oj-webapp

Web frontend of the Online Judge: a dependency-free single-page app (plain
ES modules, no build step) served by an unprivileged **nginx**, which also
reverse-proxies `/api/` to **oj-rest**.

## Features

* Problem list and problem pages with Markdown statements and samples
* Code editor with per-language starter templates, Tab indentation and
  auto-saved drafts (per problem and language)
* **Run** against custom input, and **Submit** for judging with live verdict
  updates and per-test results
* Submissions list (filter by user / problem) and submission details
* Admin page (bearer token) to create problems with test cases and delete them

## Layout

```
public/            static site (index.html, css/, js/)
  js/api.js        REST client
  js/markdown.js   tiny, escape-first Markdown renderer (safe for untrusted text)
  js/dom.js        DOM helpers (no innerHTML with untrusted data)
  js/app.js        router and views
nginx/             nginx config template (envsubst: REST_UPSTREAM)
tests/             node:test unit tests
```

## Configuration

| Variable        | Default            | Description                     |
|-----------------|--------------------|---------------------------------|
| `REST_UPSTREAM` | `http://rest:8000` | Where `/api/` is proxied to     |

## Development

```bash
npm test                         # node --test (no dependencies)
docker build -t oj-webapp .
docker run -p 8080:8080 -e REST_UPSTREAM=http://host.docker.internal:8000 oj-webapp
```

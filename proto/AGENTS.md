# AGENTS.md

Instructions for AI coding agents working in oj-proto. Read `README.md` first:
it is the architecture and contract reference for the whole Online Judge.

## Rules
- This repo only holds `.proto` files and the generator. No service code.
- After any `.proto` change: `make gen` (lints, then regenerates into every
  sibling repo) and commit the regenerated code in each affected repo.
- `make check` must pass. `buf lint` uses the STANDARD rules: `<Rpc>Request` /
  `<Rpc>Response` per RPC, enum values prefixed with the enum name, zero value
  `*_UNSPECIFIED`.
- Wire compatibility: never renumber, reuse or retype a field. Mark int64 ids
  that the webapp sees with `[jstype = JS_NUMBER]`.
- Never hand-edit generated code in any repo.

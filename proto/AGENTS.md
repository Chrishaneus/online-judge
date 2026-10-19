# AGENTS.md

Instructions for AI coding agents working in `proto/`. Read `README.md` first:
it is the architecture and contract reference for the whole Online Judge.

## Rules
- This directory only holds `.proto` files and the generator. No service code.
- After any `.proto` change: `make gen` (lints, then regenerates into every
  service) and commit the regenerated code in the same commit.
- `make check` must pass. `buf lint` uses the STANDARD rules: enum values
  prefixed with the enum name, zero value `*_UNSPECIFIED`. HTTP messages are
  named `<Action>Request` / `<Action>Response`, with the route in a comment
  above the request.
- Wire compatibility: never renumber, reuse or retype a field. int64 fields
  are `bigint` in the webapp's TS (protoc-gen-es v2 ignores `jstype`).
- Never hand-edit generated code in any service.

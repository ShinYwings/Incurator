# v0.36.1 XC-1 Evidence Ledger

Date: 2026-07-19

## Rollback Anchor

- Branch: `release/v0.36.1`
- Base / merge anchor: `b2a26e32d78479118f058cb5f60d50b9fe7ba4c8`
  (PR #88 merge on `master`)
- Worktree was clean before branch creation.

## Current Repository Reality

The old diagnosis references pre-CM-1 monoliths. Current owners and broad-handler
counts are:

```text
backend/src/curator/commands     67
backend/src/curator/mcp          69
backend/src/curator/plugin_api   12
```

AST classification found 28 handlers with syntactically silent bodies:

- commands: 5 (`common.py` 4, `plugin.py` 1)
- MCP: 22 in `server.py`
- plugin API: 1 in `query_api.py`

These include intended fallback and cleanup paths; zero raw broad catches is not
a valid target. Public CLI/MCP/plugin catch-and-envelope handlers are excluded.

## Documentation Reality

- `SYSTEM_BEHAVIOR.md` already requires best-effort runtime/config/MCP sync
  failures to be surfaced rather than silently swallowed.
- `USER_GUIDE.md` documents non-fatal config sync warnings.
- No current contract defines a universal warning field for every MCP or plugin
  API response, so this patch must not invent one.

## Prior Art

- [Python Errors and Exceptions](https://docs.python.org/3/tutorial/errors.html):
  handle only errors a layer can actually handle; log and re-raise when the
  caller owns recovery.
- [Python Logging HOWTO](https://docs.python.org/3/howto/logging.html): suppressed
  errors in long-running processes should be recorded through logging, and
  module-level loggers preserve origin/severity.
- [Python `contextlib.suppress`](https://docs.python.org/3/library/contextlib.html#contextlib.suppress):
  suppression should name the specific exceptions whose absence is intended.

## Pre-Implementation Validation

- v0.36.0 merge CI was green: Backend Tests, Plugin Tests, Version Consistency.
- No schema or data migration is planned.
- Active testbed scenario remains `gaussian_splatting`.

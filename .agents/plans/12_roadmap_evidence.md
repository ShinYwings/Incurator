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

## Confirmed Behavior Defects And Repairs

- `curator_build_source(wait=True)` returned `ok=true` when the ingest pipeline
  returned no result for the requested source. It now returns `ok=false` with a
  named error.
- Successful source builds and `curator_add_knowledge` silently discarded
  follow-up search-index failures. They now preserve the completed primary
  operation and return the degradation in `warnings`.
- `curator_get_provider_config` still resolved `data/models.json` relative to
  the pre-CM-1 MCP module location, so the current Claude/Codex catalogue was
  always empty. It now loads `curator.data/models.json` as a package resource.
- The MCP guide documented a nonexistent `provider` argument for
  `curator_set_provider_config`; it now documents the actual `primary`, model,
  host, secret, base URL, and workspace parameters.
- The runtime snapshot spec allowed absolute machine paths while the guides,
  implementation, and tests forbid them. The spec now records the portable,
  path-sanitized contract.

## Post-Implementation Validation

- Silent broad-handler policy: 28 pre-existing findings reduced to zero.
- Focused command/MCP/plugin API regression group: 81 passed.
- Full backend: 1225 passed, 6 skipped, 5 xfailed.
- Ruff: passed.
- Mypy: passed for 125 source files.
- Plugin Vitest: 66 files / 688 tests passed.
- Plugin TypeScript `--noEmit`: passed.
- Plugin production build: passed.
- Version/spec consistency group: 42 passed.
- `gaussian_splatting` testbed: `status`, `add`, `sync`, and `lint` passed;
  lint health was 100/100 with zero findings. The external Zotero Reference Mode
  row remained portable and resolvable without copying its external source.
- Knowledge Sync regression: two consecutive `wiki db autosync --skip-reindex`
  runs each reported `+0 inserted, ~0 updated, 0 deleted from 0 peer file(s)`;
  no repeated export/import loop was triggered.

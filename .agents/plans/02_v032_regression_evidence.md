# v0.32.0+ Stability Regression Audit — Active Evidence Ledger

Updated: 2026-08-01
Rollback anchor for P6: merged v0.39.2 relay-reset head `346fcdb`.

## Completed Boundary

- P1–P5 are merged; P6 is verified on the v0.39.3 release branch and its
  completed domain analysis is preserved in Git history.
- v0.39.1 closed source deletion, serving-state eviction, and deterministic
  post-publish projection recovery.
- v0.39.2 closed latest-user PDF equation-reference context recovery.
- v0.39.3 closes durable-state integrity findings F14–F16.

## P6 Findings

- F14: corrupt `sessions.json` can be mistaken for missing state and later
  overwritten by defaults.
- F15: malformed secret storage can collapse to `{}` and lose credentials on
  the next write.
- F16: runtime status shallow-copy can expose nested legacy credentials.

Required proof: byte preservation, fail-closed saves, atomic serialized writes,
concurrent/interrupted write tests, synced-session merge tests, and recursive
redaction fixtures.

### P6 Validation Record — v0.39.3

- Branch/base: `release/v0.39.3` from `346fcdb`.
- Red phase: focused backend collection failed because `curator.durable_io` did
  not exist; focused plugin tests failed because the typed session store did not
  exist and `main.ts` still conflated missing/corrupt state.
- Contracts: updated the plugin/session and sync guides (English first, Korean
  synchronized), plugin schema, and system behavior spec for typed canonical
  reads, fail-closed mutation, atomic serialization, and recursive redaction.
- Implementation: added per-path locked atomic backend writes; routed secret,
  global/project config, CLI config-set, and schema-version mutations through
  them; added typed atomic plugin JSON/session stores and wired session/Zotero
  persistence through them; recursively removed credential-bearing snapshot
  keys.
- Focused proofs: corrupt bytes survive failed mutation; missing/corrupt/
  unreadable and structurally invalid session state remain distinct; 24 secret
  and 32 config concurrent updates retain unrelated keys; interrupted backend
  replacement and plugin rename preserve the prior target and remove temps;
  Linux/macOS/remote sessions merge; nested credential fixtures are absent.
- Full release-head local gates: backend `pytest` 1,382 passed / 6 skipped / 4 xfailed;
  Ruff clean; mypy clean across 127 source files; plugin production build clean;
  Vitest 69 files / 749 tests passed; version/spec consistency 10 passed.
- Testbed/Reference Mode: not run because P6 changes only durable local state
  and its approved plan forbids mutating the active testbed or production vault;
  all proofs use isolated temporary directories and mocked vault adapters.
- Production-path restoration: no production or active-testbed path was read or
  written; no path override was changed.

## P7 Findings

- F09–F13: shared cancellation, non-streaming CLI model/PATH drift, lossy MCP
  names, unsettled shutdown promises, and unbounded backend subprocesses.

Required proof: overlapping request tests, dismiss/abort tests, MCP collision
and restart tests, hung-process timeout tests, and legitimate long-command
tests.

## P8 Findings

- F08 and F19–F22: hidden vector degradation, short/invalid provider outputs,
  stale primary attribution after failover, and lexical prompt-version sorting.

Required proof: lexical fallback, vector-only failure, short/long/NaN provider
outputs, failover trace attribution, and v9/v10 ordering tests.

## Validation Record Template

Each patch appends: branch and merge-base; failing tests; changed contracts;
focused and full gate results; isolated testbed and Reference Mode results;
production-path restoration check; release commit; PR and latest-head CI.

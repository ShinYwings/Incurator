# v0.32.0+ Stability Regression Audit — Active Evidence Ledger

Updated: 2026-08-01
Rollback anchor for P7: merged v0.40.0 relay-reset head `57665c7`.

## Completed Boundary

- P1–P6 are merged; P6 shipped in v0.40.0 after persistence review hardening
  and its completed domain analysis is preserved in Git history.
- v0.39.1 closed source deletion, serving-state eviction, and deterministic
  post-publish projection recovery.
- v0.39.2 closed latest-user PDF equation-reference context recovery.
- v0.40.0 closes durable-state integrity findings F14–F16 plus commit-boundary
  config/plugin merge and permission regressions found during review.

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
- Delivery: implementation commit `932fbc1`; release commit `272c7fa`; draft
  PR #104: `https://github.com/ShinYwings/Incurator/pull/104`.
- GitHub CI passed on delivery head `953a408`: backend, plugin, and version
  consistency all green for push/PR events (one duplicate version job skipped).
- Review follow-up promoted the unreleased patch to v0.40.0 because atomic
  plugin processing requires Obsidian 1.1.0. Successor PR #105 merged as
  `066a158`; final local/backend/plugin gates and latest-head CI were green.

## P7 Findings

- F09–F13: shared cancellation, non-streaming CLI model/PATH drift, lossy MCP
  names, unsettled shutdown promises, and unbounded backend subprocesses.

Required proof: overlapping request tests, dismiss/abort tests, MCP collision
and restart tests, hung-process timeout tests, and legitimate long-command
tests.

### P7 Baseline — v0.40.1

- Branch/base: `release/v0.40.1` from clean merged relay-reset head `57665c7`.
- Target: patch v0.40.1; no schema/public-contract change is planned.
- Docs-first contract update: plugin lifecycle, external MCP, Quick Query, and
  backend command bounds are synchronized in the English guide, Korean guide,
  and plugin schema.
- Red phase: 8 focused failures reproduced request overlap/foreground restore,
  caller-owned CLI cancellation, dropped CLI model/PATH, MCP identifier
  collision, pending shutdown, missing forced kill, stale restart exit, and the
  absent backend-boundary module. The remaining 67 focused tests passed.
- Green phase: `npx tsc --noEmit` plus 107 focused provider/MCP/backend/Quick
  Query tests passed; the latest focused lifecycle set passes 100/100 after
  cancellation shutdown hardening.
- Full plugin validation from `plugin/`: 769/769 Vitest tests passed and the
  production bundle built. A root-cwd Vitest invocation was discarded because
  `pluginCompatibility.test.ts` intentionally resolves manifests from the
  plugin working directory; the canonical plugin-cwd invocation is green.
- Full repository gates: backend 1386 passed / 6 skipped / 4 xfailed, Ruff
  passed, mypy passed, plugin 769/769 passed, TypeScript passed, production
  plugin build passed, and post-bump spec/version sync passed 10/10.
- Testbed/Reference Mode: not run for P7. These defects are device-local
  provider/process lifetime boundaries with deterministic fake-process tests;
  the active scenario was not identified, and the approved P7 boundary forbids
  mutating the existing testbed or production `second_brain` for these proofs.
- Implementation commit: `033a4fd` (`fix(plugin): harden provider and process
  lifetimes`); release commit: `d626a5d` (`chore(release): v0.40.1`).
- Delivery: draft PR #106, `https://github.com/ShinYwings/Incurator/pull/106`.
  GitHub CI passed on release head `d626a5d`: backend and plugin jobs were green
  for both push/PR events, version consistency was green for the push event,
  and the duplicate PR-event version job correctly skipped.

## P8 Findings

- F08 and F19–F22: hidden vector degradation, short/invalid provider outputs,
  stale primary attribution after failover, and lexical prompt-version sorting.

Required proof: lexical fallback, vector-only failure, short/long/NaN provider
outputs, failover trace attribution, and v9/v10 ordering tests.

## Validation Record Template

Each patch appends: branch and merge-base; failing tests; changed contracts;
focused and full gate results; isolated testbed and Reference Mode results;
production-path restoration check; release commit; PR and latest-head CI.

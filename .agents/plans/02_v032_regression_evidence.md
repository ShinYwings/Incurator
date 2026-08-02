# v0.32.0+ Stability Regression Audit — Active Evidence Ledger

Updated: 2026-08-01
Rollback anchor for P8: clean merged v0.40.1 relay-reset head `710817c`.

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

### P7 Review Follow-Up Baseline — PR #106 head `4b354fd`

- RF1 reproduced by inspection: `beginRequest(ownerSignal)` still assigns the
  global foreground pointer while sidebar Stop/session paths call the unscoped
  `LLMClient.abort()` API.
- RF2 reproduced by inspection: Quick Query creates its controller before
  asynchronous PDF reference resolution, while provider methods do not reject
  an already-aborted signal before launch; streaming CLI calls `spawn` before
  checking the signal and non-streaming HTTP eagerly constructs `requestUrl`.
- RF3 reproduced by inspection: both Ollama catch blocks classify `AbortError`
  as provider failure before the cancellation-aware outer path can observe it.
- RF4 reproduced by inspection: MCP `error`/`exit` callbacks compare process
  identity but stdout always feeds the instance-wide buffer, which is never
  cleared on restart.
- Rollback anchor for the review follow-up is pushed PR head `4b354fd`; the
  worktree was clean before planning. No vault, testbed, DB, or external
  reference state is involved.

### P7 Review Follow-Up Validation

- Red phase: 6 failures across 3 files reproduced the wrong foreground target,
  eager `requestUrl`/CLI launch, both Ollama cancellation mappings, and stale
  MCP stdout buffer poisoning; the other 76 focused tests passed.
- Green phase: 109 focused provider/MCP/Quick Query/backend lifecycle tests and
  TypeScript passed after implementation.
- Full local gates: plugin Vitest passed 778/778 and the production bundle
  built; backend pytest passed 1386 with 6 skipped and 4 expected failures;
  Ruff passed; mypy passed across 127 source files; `git diff --check` passed.
- No version change is required because v0.40.1 remains unreleased and all
  manifests already agree. `CHANGELOG.md`, the English/Korean plugin guides,
  and plugin schema now describe the hardened boundary.
- Testbed/Reference Mode remains out of scope: the follow-up changes only
  device-local provider/process lifetime code with deterministic fake-process
  coverage. No production or testbed path/configuration was read or modified.
- Delivery commit `0258536` (`fix(plugin): close lifecycle review gaps`) is
  pushed to PR #106. On that exact head, both backend jobs and both plugin jobs
  passed; push-event version consistency passed and its duplicate PR-event job
  correctly skipped.

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

### P8 Baseline — v0.40.2

- Branch/base: `release/v0.40.2` from clean merged relay-reset head `710817c`.
- Target: patch v0.40.2; no schema, command, setting, or ranking-policy change.
- Confirmed code boundaries: `HybridEngine._vector_list` turns every query
  embedding exception or empty response into an untraced empty vector list;
  `_rerank` and `embed_corpus` accept provider prefixes through `zip` and do
  not reject non-finite scores/vectors; `run_prompt` records provider/model only
  before `FailoverClient` selects a successful provider; `PromptRegistry`
  compares versions lexicographically.
- Frozen D2 boundary: `D2_HOLDOUT_RESULT.yml` is consumed (`run_count: 3`) and
  pins `retrieval/engine.py` plus `retrieval/embedding.py`. Its accepted Q06
  configuration is DB-native lexical FTS5/BM25 with `rerank: false`,
  `providers: none`, and no model judges. P8 changes only provider-present
  vector/reranker branches, so the accepted ranking inputs and metric are
  unaffected. Re-arm the two fingerprints after implementation; do not rerun
  the holdout.
- Testbed/Reference Mode boundary: the existing testbed resembles the historical
  `complex_math_backprop` scenario and includes retired EXH-era assertions. P8
  uses temporary current-schema databases and deterministic fake providers;
  do not reinitialize or mutate that unrelated testbed or production vault.

### P8 Validation — v0.40.2

- Red phase: 15 failures across engine, embedding, prompt registry, and prompt
  trace tests reproduced silent hybrid/vec-only embedding failure, short/long/
  NaN reranker and corpus-embedding output, stale failover attribution,
  lexicographic v9/v10 lookup, and acceptance of malformed versions. The other
  32 focused tests passed.
- Green phase: the focused engine, embedding, prompt registry, prompt trace, and
  DB schema set passed 63/63. Invalid embedding batches persist no prefix;
  invalid reranker results keep both seeded RRF candidates; successful failover
  traces name `claude-code` and its fallback model.
- Full local gates: backend pytest passed 1,401 with 6 skipped and 4 expected
  failures; Ruff passed; mypy passed across 127 source files; plugin Vitest
  passed 778/778 across 73 files; TypeScript passed; and the production plugin
  bundle built. The full backend run also passed the D2 fingerprint, docs parity,
  and v0.40.2 version/spec consistency tests.
- Frozen holdout: re-armed `retrieval/engine.py`, `retrieval/embedding.py`, and
  `db/_entities.py` hashes with the lexical-only Q06 non-impact proof. The
  consumed holdout was not rerun and no new evaluation result is claimed.
- Testbed/Reference Mode: not run. The active scenario was not identified and
  the existing testbed is an unrelated historical backprop/EXH-era fixture;
  P8's provider boundaries are fully exercised with current-schema temporary
  DBs and deterministic fake providers. No production or testbed path/config
  was read, written, or overridden.
- Implementation commit: `a9792e3` (`fix(core): enforce retrieval and prompt
  integrity`); release commit: `1760397` (`chore(release): v0.40.2`).
- Delivery: draft PR #107,
  `https://github.com/ShinYwings/Incurator/pull/107`. GitHub CI passed on
  delivery head `de7a541`: both backend jobs and both plugin jobs were green,
  push-event version consistency was green, and the duplicate PR-event version
  job correctly skipped.

### P8 Review Follow-Up Baseline — PR #107 head `a423a38`

- RF5 reproduced: an exact two-row embedding response with dimensions 2 and 3
  returns `embedded=2`, `failures=0`, persists both dimensions under one
  provider/model, and makes the next vector search fail while reshaping five
  floats as two two-dimensional rows.
- RF6 reproduced: a two-dimensional query against a ready three-dimensional
  corpus returns an empty `vec_raw` with `fallback_mode=""` and no warning.
- RF7 reproduced: fallback `ClaudeCodeClient` produces the valid response, then
  a primary probe succeeds during delayed validation; the completed PTR records
  `ollama` / `primary-model` with `active_idx=0`.
- Rollback anchor: pushed clean PR head `a423a38`. The worktree was clean before
  these review-plan artifacts; no application code has been changed.
- Validation boundary: reproductions used temporary current-schema SQLite DBs
  and deterministic fake providers. The active testbed, production vault, and
  consumed D2 holdout were not read or mutated.

## Validation Record Template

Each patch appends: branch and merge-base; failing tests; changed contracts;
focused and full gate results; isolated testbed and Reference Mode results;
production-path restoration check; release commit; PR and latest-head CI.

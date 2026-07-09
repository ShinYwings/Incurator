# RELAY — release/v0.33.0 review fixes

## Goal

Address code-review findings on `release/v0.33.0`.

## Plan Reference

No active plan file. This was review-fix follow-up work on the existing release branch.

## Analysis & Reasoning

- Restored monotonic `updated_at` trigger advancement for `sources` and
  `compiler_generations` when the device clock is equal to or behind the row
  revision.
- Repaired lint fixers to resolve generated DAG pages through
  `.curator/Collections/` via `paths.collections`.
- Removed obsolete tests that asserted deleted legacy migration helpers and
  cleaned config/schema imports left by the cleanup.
- Tightened JSONL source import to require current-schema `sync_key` and
  `updated_at` instead of deriving legacy revisions from `last_ingested` /
  `added_at`.
- Fixed `connect()` self-heal to stamp `schema_version` with the current
  `SCHEMA_VERSION` without reintroducing legacy migrations.
- Checked local `.cache/vaults/13ed51f8b06cb88e/state.sqlite`: it is now stamped
  `schema_version=12`, has the required current indexes/triggers, and currently
  has zero source/generation rows. `.curator/sync` has no peer files; sync state
  uses `last_export_id` and has no `last_imported_mtime`.
- Updated specs/guides and the D2 holdout hash ledger to match v0.33.0 strict
  schema behavior.
- The additional pasted “review” attachment was a vault sync-report dump, not a
  branch code review. It appears to describe content-level DAG issues rather than
  release-code defects.

## Progress Status

Implemented and locally verified. Changes are uncommitted on `release/v0.33.0`.
Full backend pytest passed after the D2 hash ledger was re-armed. Focused schema
and sync tests also passed after the local DB stamp check.

## Critical Context / Blockers

No current blocker. Full pytest emits existing SWIG/Fitz deprecation warnings in
PDF-context tests.

## Immediate Next Action

Commit the review fixes and push the branch if the user wants the PR updated.

### Update (2026-07-09, Codex) — second_brain vault refresh

- Connected vault resolved to `/Users/shin/shinywings/second_brain` with cache key
  `13ed51f8b06cb88e`.
- Ran `wiki add`, `wiki build`, `wiki reindex --embed`, and
  `wiki sync --no-deep --no-interactive` against that vault.
- Final DB checks: `PRAGMA integrity_check` = `ok`, `schema_version=12`,
  `sources=33` with no missing `sync_key`/`updated_at`,
  `compiler_generations=33`, `knowledge_units=1770`, `graph_entities=691`,
  `graph_relations=675`, `search_documents=3255`, `search_chunks=3259`,
  `search_embeddings=3259`, and no unfinished ingest jobs.
- Final `wiki status`: L1 33/33, L2 33/33, L3 3 done / 30 skipped, L4 33/33.
  Latest sync report was refreshed by `sync`, with `logical gaps=0`,
  `safe-fixed=10`, and `needs-review=574`.
- Autosync dry-run reports `+0 inserted, ~0 updated, 0 deleted`; peer JSONL
  headers are current-schema `schema_version=12`.

### Update (2026-07-09, Codex) — L3/L4 and sync projection repair

- User was right that the earlier L3/L4 interpretation was too loose. The code
  now fixes the root causes instead of only changing docs:
  - existing DB trigger bodies are refreshed on connect/init, so stale
    `updated_at` triggers are replaced;
  - L4 source status is derived only from sources grounded in synthesis/report
    provenance, and stale layer statuses without `layer_error` are healed from
    DB truth during projection re-emit;
  - SYN nodes store `concept_ids`, SYN markdown emits `03_Concepts/CON-*`
    links, Concept pages emit Atom relation wikilinks, and Atom re-emits retain
    `source_path`;
  - CON ids are deterministic per community report, preventing repeated
    delete/new churn on re-emit;
  - source-derived `[[Note#Heading]]` links in generated CTX projection text are
    rendered as plain text so `wiki add` does not create immediate malformed
    wikilink review items;
  - failed/stale/unchecked compiler claims are reported as nonblocking telemetry
    when excluded from serving, not as sync review blockers;
  - sync page-hash updates now prune deleted projection hashes, so deleted
    pages do not stay dirty forever.
- Applied the repaired projection to `/Users/shin/shinywings/second_brain`.
  Latest `wiki status` shows 33 sources, 481 collection pages, L1 33 done, L2
  23 done / 10 skipped, L3 23 done / 10 skipped, L4 23 done / 10 skipped.
- Verified with repeated real sync:
  `VAULT_ROOT=/Users/shin/shinywings/second_brain uv run wiki sync --no-deep --no-interactive`
  now reports `No manual changes detected (cached 481 pages)` and
  `No logical or structural gaps detected`.
- Latest sync report is clean: `health=clean`, `needs_review=0`,
  `blocked_logical_checks=0`, `structural_issues=0`, `logical_gaps=0`.

### Update (2026-07-09, Codex) — full regression verification

- Full backend pytest initially exposed 4 regressions:
  - D2 holdout hash ledger needed re-arming for `backend/src/curator/db/schema.py`;
  - trigger refresh DDL ran on every `db.connect()`, which locked nested read
    connections opened inside an active publish transaction.
- Fixed trigger refresh so `connect()` checks `sqlite_master` and only replaces
  trigger bodies when they are missing/stale; fresh/current DBs no longer run
  DDL on ordinary nested connections.
- Re-ran checks:
  - `scripts/backend-check ruff` → passed;
  - failed focused tests → `4 passed`;
  - full `scripts/backend-check pytest` → `1192 passed, 6 skipped, 5 xfailed`;
  - `scripts/backend-check mypy` → passed.

### Update (2026-07-09, Codex) — source-update, MCP, and formula validation

- User pushed on whether source edits, MCP usability, recovery commands, and
  LaTeX/vector search had actually been proven. That uncovered one real bug:
  bare `wiki add` auto-discovery skipped already-tracked source relpaths before
  calling `ingest_raw.add_file`, so changed existing source files were not
  content-hash checked and did not reset L2/L3/L4 to pending.
- Fixed `_auto_discover_pending()` to scan both new and existing raw-dir files
  through `ingest_raw.add_file()`. Added
  `test_modified_source_add_then_build_reprocesses_pending_source`, proving
  source edit → `wiki add --no-sync` resets downstream layers → `wiki build
  --wait --no-sync` processes the pending source.
- MCP/source recovery validation passed:
  `test_register_build_split.py`, `test_mcp_source_tools.py`,
  `test_mcp_source_status_tools.py`,
  `test_source_retry_accepts_layer_error_without_aggregate_error`, and the lint
  fixer recovery tests all passed.
- LaTeX/formula validation passed:
  `test_math_parsing.py`, `test_plan_b_support.py`,
  `test_plan_b_formula_recovery.py`, `test_vision_resolvers.py`,
  `test_plugin_pdf_transcribe.py`,
  `test_merge_raw_text_fallback_preserves_omitted_math_lines`,
  `test_chunking_never_truncates_formula_bearing_unit`, and
  `test_context_service_source_section_preserves_formula_code_citation_boundaries`
  all passed.
- Real `second_brain` formula/search check:
  source_spans with `$...$`: 391; knowledge_units with `$...$`: 571;
  collection markdown files with LaTeX: 95; search_documents with `$...$`: 477;
  search_chunks with `$...$`: 480. Formula statuses include 660
  `preserved_in_text`, 157 `uncertain`, and 85 `missing`.
- Rebuilt real `second_brain` DB-native search with embeddings:
  `wiki reindex --embed` → 3255 documents, 3259 chunks, 3259 embeddings.
  Hybrid search then ran without vector fallback warnings and returned
  formula/equation-bearing evidence for Gaussian rendering queries.
- Found a quality gap, not a release blocker: L4/community reports currently
  abstract away formulas more than ideal. Added prompt/spec/docs contract that
  community-report synthesis and query answers must preserve central equations,
  formulas, and code expressions exactly when needed.
- Final verification after these changes:
  `scripts/backend-check ruff` passed;
  focused tests passed (`112 passed`);
  `VAULT_ROOT=/Users/shin/shinywings/second_brain wiki sync --no-deep
  --no-interactive` reported no logical or structural gaps;
  `scripts/backend-check mypy` passed;
  full `scripts/backend-check pytest` passed with
  `1194 passed, 6 skipped, 5 xfailed`.

### Update (2026-07-09, Codex) — prompt review and reindex speed fix

- Continued the review for prompt quality, latent bugs, and speed. Found a
  concrete performance bug in DB-native search rebuild:
  `materialize_search_documents()` cleared `search_documents`, which cascaded to
  `search_chunks` and `search_embeddings`, defeating `embed_corpus()`'s
  unchanged-chunk skip logic. As a result, `wiki reindex --embed` rebuilt all
  3259 vectors on an unchanged `second_brain` vault.
- Fixed the root cause:
  - materializer snapshots ready embeddings before rebuild and restores vectors
    for rematerialized chunks with the same `chunk_id` + `input_hash`;
  - `wiki reindex --embed` and `search.update_index(embed=True)` now avoid
    loading the heavy embedder entirely when provider/model coverage is already
    complete;
  - search document, FTS, chunk, and restored embedding writes are batched in
    transactions instead of opening thousands of SQLite connections;
  - CLI output now distinguishes new vs reused embeddings.
- Real `second_brain` timing:
  - after preserving embeddings but before batch restore/model-load fast path:
    `wiki reindex --embed` fell to ~25s with `0 new embeddings, 3259 reused`;
  - after batching and fast path: `wiki reindex --embed` reports
    `3255 documents, 3259 chunks, 0 new embeddings, 3259 reused` in ~1.4s.
- Prompt review follow-up:
  - community-report, local-answer, and global-answer prompt contracts now state
    that central equations, formulas, and code expressions must be preserved
    exactly when needed for a finding/explanation/answer;
  - `SYSTEM_BEHAVIOR.md`, `USER_GUIDE.md`, `USER_GUIDE_KR.md`,
    `WORKFLOW_GUIDE.md`, and `WORKFLOW_GUIDE_KR.md` were updated to match.
- Added/updated tests:
  - source edit add/build reprocessing;
  - prompt formula/code preservation contract;
  - embedding coverage rejects stale hashes;
  - materializer preserves unchanged embeddings across rebuild;
  - CLI reports new/reused embeddings;
  - `search.update_index(embed=True)` skips embedder load when vectors are
    already current.
- Verification:
  - focused prompt/math/MCP/source/search suite: `136 passed`;
  - search/embedding/D2 focused suite: `25 passed`;
  - `scripts/backend-check ruff`: passed;
  - `scripts/backend-check mypy`: passed;
  - full `scripts/backend-check pytest`: `1198 passed, 6 skipped, 5 xfailed`;
  - `git diff --check`: clean;
  - real `wiki status` for `/Users/shin/shinywings/second_brain`: clean sync
    report, L1 33 done, L2/L3/L4 23 done / 10 skipped, embeddings 3259/3259.

### Update (2026-07-09, Codex) — second speed-audit correction

- User correctly challenged the previous "complete" status. A follow-up review
  found the first speed fix still had a large-vault weakness: it preserved
  embeddings by snapshotting ready vector BLOBs into Python memory and restoring
  them after deleting the corpus. That is acceptable for `second_brain`, but not
  robust for larger vaults.
- Replaced the snapshot/restore design with truly incremental materialization:
  - `search_documents` now use `ON CONFLICT DO UPDATE` instead of
    `INSERT OR REPLACE`, so child chunks/embeddings are not cascade-deleted for
    unchanged docs;
  - stale documents are removed using a temporary current-doc table;
  - `search_chunks` likewise use `ON CONFLICT DO UPDATE`, and stale chunks are
    removed using a temporary current-chunk table;
  - changed chunks still delete their stale embeddings via FK cascade, while
    unchanged chunks keep their embeddings in place without copying vector BLOBs.
- Added a regression test proving changed search document text removes stale
  chunk embeddings.
- Real `second_brain` check still reports:
  `wiki reindex --embed` → `3255 documents, 3259 chunks, 0 new embeddings, 3259 reused`
  in ~1.1s, with `search_chunks=3259` and `search_embeddings=3259`.
- Verification after this correction:
  - search/embedding/D2 focused suite: `26 passed`;
  - `scripts/backend-check ruff`: passed;
  - `scripts/backend-check mypy`: passed;
  - full `scripts/backend-check pytest`: `1199 passed, 6 skipped, 5 xfailed`;
  - `git diff --check`: clean;
  - real `wiki status` for `/Users/shin/shinywings/second_brain`: clean.

### Update (2026-07-09, Codex) — review follow-up fixes

- User asked whether the latest review findings were actually fixed and pushed.
  They were not yet fixed at that moment; this follow-up fixed both findings.
- Fixed embedding reuse fast path:
  - `search.update_index(embed=True)` and `wiki reindex --embed` now only skip
    embedder construction when current DB vectors are complete AND the configured
    embedding identity is available.
  - llama-cpp availability is checked without loading the GGUF: package presence
    plus configured/cache model-file existence.
  - If the configured embedder is unavailable, reindex degrades explicitly to
    FTS5-only instead of reporting reused vectors as ready.
- Fixed L4 projection re-emit churn:
  - `reemit_projections()` now updates `synthesis_nodes.concept_ids` and
    `updated_at` only when the computed concept ids actually change.
  - No-op re-emits no longer advance synthesis LWW revisions or create sync
    dirtiness.
- Added regression coverage:
  - current vectors + missing llama-cpp model path degrade instead of falsely
    succeeding;
  - repeated L4 re-emit with unchanged concept ids preserves `updated_at`.
- Updated `SYSTEM_BEHAVIOR.md`, `USER_GUIDE.md`/`_KR`, and
  `WORKFLOW_GUIDE.md`/`_KR` to match.
- Verification:
  - focused search/reemit/materializer/embedding suite: `28 passed`;
  - D2 holdout check: `1 passed`;
  - `scripts/backend-check ruff`: passed;
  - `scripts/backend-check mypy`: passed;
  - full `scripts/backend-check pytest`: `1201 passed, 6 skipped, 5 xfailed`;
  - `git diff --check`: clean;
  - real `second_brain` `wiki reindex --embed`: `3255 documents, 3259 chunks,
    0 new embeddings, 3259 reused` in `real 1.17s`.

### Update (2026-07-09, Codex) — macOS/Linux cross-device config guard

- User flagged likely cross-device problems when alternating between Linux and
  macOS. Found a real risk: `save_config()` already routes machine-local blocks
  (`llm`, `search`, `external`) to repo-local `.cache/config/config.yml`, but
  `load_config()` still merged those blocks if stale copies existed in synced
  `.curator/settings.yml`.
- Fixed `load_config()` to ignore machine-local keys from synced vault config.
  This prevents macOS absolute model/Zotero/external paths from overriding Linux
  local paths, and vice versa, without rewriting the synced settings file.
- Added regression coverage proving synced vault `llm`/`search`/`external`
  blocks are ignored while vault-shared keys such as `paths` and `persona`
  still load normally.
- Updated `SCHEMA.md`, `USER_GUIDE.md`/`_KR`, and `PLUGIN_GUIDE.md`/`_KR` to
  document the strict split.
- Verification:
  - cross-device/config focused tests: `70 passed`;
  - `scripts/backend-check ruff`: passed;
  - `scripts/backend-check mypy`: passed;
  - spec sync + D2 holdout focused tests: `11 passed`;
  - `git diff --check`: clean;
  - real `second_brain` `wiki status`: clean sync report, no pending/error
    layer work.

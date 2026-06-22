# Diagnosis: G01-ingest-core

Coverage:
- `backend/src/curator/ingest_raw.py` (2346 lines) — read in full (4 chunks).
- `backend/src/curator/ingest_llm.py` (729 lines) — read in full.
- `backend/src/curator/ingest_worker.py` (467 lines) — read in full.
- `backend/src/curator/ingest_orchestrator.py` (35 lines) — read in full.
- Supporting context read for correctness judgement: `db.py` (schema DDL for `sources`/`dag_edges`/`source_pdf_pages`/`source_pages`/`ingest_jobs`/`job_events`, `connect()`, `claim_next_job`, `count_active_l2_jobs`, `update_job_progress`, `mark_job_done`, `insert_dag_edge`, `recover_stale_jobs`, `set_source_layer_status`), `constants.py` (STATUS_*/PHASE_*), `pipeline/compile.py` (callback usage check), and caller cross-refs in `cli.py`/`backprop_agents.py`. CLAUDE.md invariants applied (EXH/L4-per-workspace retirement, DB = source of truth).

## Findings

### [G01-ingest-core-1] (a/h) S1 — `remove_source` raises IntegrityError / leaves orphans because it never deletes `dag_edges`, `ingest_jobs`, `job_events`
- Loc: backend/src/curator/ingest_raw.py:2318-2331 (remove_source); contrast db.py:250-260 (dag_edges FK), db.py:1260 (PRAGMA foreign_keys = ON)
- Evidence: `remove_source` only deletes from `source_pages`, `ingest_runs`, and `sources`. But `dag_edges.source_id` is `INTEGER REFERENCES sources(id)` with NO `ON DELETE` action, and `connect()` enables `PRAGMA foreign_keys = ON`. CTX→ATM edges are inserted with the integer `source_id` (db.insert_dag_edge, called from the compile pipeline). So once a source has been compiled to L2, deleting it via `wiki sources rm` will hit a foreign-key RESTRICT and raise `sqlite3.IntegrityError`, aborting the whole delete transaction. The companion path `_auto_discover_pending` (ingest_llm.py:286-294) DOES delete `job_events`, `ingest_jobs`, `ingest_runs`, `source_pages`, `dag_edges`, `source_pdf_pages` before deleting the source — proving the correct cascade set is known, but `remove_source` is missing it. `source_pdf_pages` happens to cascade automatically, but `dag_edges` does not.
- Fix sketch: Mirror the deletion set used in `_auto_discover_pending`: delete `job_events` (via subselect on `ingest_jobs`), `ingest_jobs`, `dag_edges` for the source before deleting `sources`. Or add `ON DELETE CASCADE` to `dag_edges.source_id` (needs migration) and to `ingest_runs`/`source_pages`.
- Blast radius: `wiki sources rm`, MCP `curator_remove_source`, any orphan-cleanup path. A failed delete leaves the DB in the pre-delete state (transaction rolls back) — user-visible "remove failed" + stale rows.
- Suggested PR: fix/remove-source-cascade

### [G01-ingest-core-2] (e/f) S2 — `callbacks_factory` is accepted but never invoked: dashboard L2/L3 progress is dead
- Loc: backend/src/curator/ingest_llm.py:508 & 584 (params); backend/src/curator/ingest_worker.py:48-90 (WorkerCallbacks), 158-159, 215-217 (factory passed in)
- Evidence: `run_l1_to_l3` and `run_l3_from_existing_atoms` take `callbacks_factory: Callable[[], IngestCallbacks]` but the body never calls it; they delegate straight to `_compile.compile_source_l2` / `compile_global_l3`, and `pipeline/compile.py` has zero references to `callback`. The worker builds `WorkerCallbacks` (on_pass1_start/on_fragment_written/on_pass2_start/on_theme_written) and passes a factory, but those handlers are never triggered, so the live per-fragment/per-theme progress fields the dashboard renders are never updated from inside the compile run. Worker-side progress only updates at coarse fixed points (0.1, 0.5, 0.75). The whole rich `IngestCallbacks` surface (on_stream_chunk, on_pass3_start, on_curation_*, on_theme_drafting, on_fragment_drafting, on_finalizing) is inert relative to the v0.3.1 compile pipeline.
- Fix sketch: Either thread the factory into `compile_source_l2`/`compile_global_l3` and emit real events, or delete the unused parameter and the unreachable callback methods. Decide one direction; current state is misleading wiring.
- Blast radius: Plugin build dashboard progress accuracy; no crash, just stale/coarse progress. Removing params touches worker + any cli callers.
- Suggested PR: fix/ingest-callbacks-wiring (or chore/remove-dead-callbacks)

### [G01-ingest-core-3] (d) S3 — `find_workspace_exhibition` is dead code referencing retired per-workspace L4/EXH
- Loc: backend/src/curator/ingest_llm.py:713-729
- Evidence: No caller anywhere in `backend/src/curator` (grep returns only the definition). It scans `paths.synthesis` for `SYN-*` (code says PREFIX_L4) frontmatter `workspace == project`, a concept tied to per-workspace Exhibitions which CLAUDE.md and the storage/curation memory explicitly mark as REMOVED ("Static/frozen Exhibition files (EXH-*.md) are REMOVED ... curation = dynamic lens, never stored as a file"). The docstring still talks about "Exhibition tagged for this workspace project."
- Fix sketch: Delete the function (verify no plugin/MCP indirect reference first).
- Blast radius: None (unreferenced).
- Suggested PR: chore/legacy-sweep-ingest

### [G01-ingest-core-4] (h/a) S2 — L3-only job path never records token usage
- Loc: backend/src/curator/ingest_worker.py:155-173 (early return) vs 227-243 (token accounting only on L2 path)
- Evidence: When a job is `PHASE_L3` (standalone global clustering, enqueued by `enqueue_l3_global`), `run_next_job` calls `run_l3_from_existing_atoms` and returns at line 164-170 BEFORE the `get_and_reset_token_usage` / `accumulate_job_tokens` block. The L3 clustering does consume LLM tokens (community reports / concept projection), but they are silently dropped and never persisted to `ingest_jobs`. The same client.get_and_reset is also not called, so on a `FailoverClient` the counters leak into the next job's reset.
- Fix sketch: Factor the token-capture block (227-243) into a helper and call it on both the L3-only and L2 return paths (before `mark_job_done`/return).
- Blast radius: Per-job token/cost reporting under-counts standalone L3 jobs; cross-job counter bleed.
- Suggested PR: fix/l3-job-token-accounting

### [G01-ingest-core-5] (b) S3 — Two near-identical JSON-extraction + LaTeX-escape-repair implementations duplicated across the module pair
- Loc: ingest_llm.py:140-208 (`_extract_json`, `_parse_json_model._sanitize_string_content`) vs ingest_raw.py:495-577 (`_extract_json_object`, `_loads_json_relaxed._repair_string_escapes`)
- Evidence: Both files independently implement (1) a brace-depth scanner that strips ``` fences and returns the first top-level `{...}` block, and (2) a regex `re.sub(r'"([^"\\]|\\.)*"', ...)` that walks string contents repairing stray backslashes (`'"\\/bfnrt'`, `\uXXXX` passthrough). The inner repair loops are character-for-character the same logic. This is copy-pasted JSON-repair code; a bug fix in one will not propagate to the other.
- Fix sketch: Extract a shared `json_repair` helper (e.g. in a small util module) and have both call sites use it.
- Blast radius: L1 summary parsing (ingest_raw) and conversational-atom/summary parsing (ingest_llm); behavior-preserving refactor with test coverage.
- Suggested PR: chore/dedupe-llm-json-repair

### [G01-ingest-core-6] (b) S3 — Redundant double JSON extraction in `add_atom_from_insight`
- Loc: backend/src/curator/ingest_llm.py:641
- Evidence: `_parse_json_model(_extract_json(raw), SummaryData)` — but `_parse_json_model` already calls `_extract_json(raw)` on its first line (line 174). So `_extract_json` runs twice on the same text. Harmless but confusing; signals the helper contract is unclear.
- Fix sketch: Call `_parse_json_model(raw, SummaryData)` directly.
- Blast radius: None functional.
- Suggested PR: chore/dedupe-llm-json-repair (bundle)

### [G01-ingest-core-7] (c/h) S2 — `_apply_vlm_pdf_extraction` failure aborts the entire L1 generation for that source
- Loc: backend/src/curator/ingest_raw.py:1315-1325 (call site) and 1428-1508 (impl)
- Evidence: In `generate_l1_structural_context`, the whole PDF VLM block is inside the same `try` whose `except` (1322-1325) marks `l1` status `error` and returns None. Per-page transcription failures are caught and fall back to pymupdf4llm text (good), but a failure in `vision.render_pdf_pages` (e.g. a corrupt page, OOM, or a bad-but-built vision client raised by `_require_vision` at 1317) raises out of `_apply_vlm_pdf_extraction` and kills L1 for the source — even though a perfectly good structural L1 could have been produced from the parser text alone. The docstring at 1312-1314 calls this intentional ("configured-but-bad vision model → l1 error"), but render/transcription infra failures are conflated with config errors and the source gets no L1 at all.
- Fix sketch: Narrow the try so only `_require_vision`/config-resolution errors hard-fail; wrap the `render_pdf_pages` + transcription in its own guard that logs and continues with parser text (the per-page fallback already exists for the LLM call, just not for render/build).
- Blast radius: A single bad PDF or transient vision-infra hiccup blocks L1 for that document; affects `wiki add` of PDFs when `vision_model` is set.
- Suggested PR: fix/vlm-extraction-soft-fail

### [G01-ingest-core-8] (c) S3 — Bare `print` warnings instead of logging; several broad `except Exception: pass`
- Loc: ingest_raw.py:491 (`print("    [Warn] Vision inference failed: {e}")`), 1152-1153 (`_save_pdf_images` swallow), 1363-1364, 1306, 1480; ingest_llm.py:683-684 (`add_atom_from_insight` returns None on any Exception), 727-728; ingest_worker.py:198-199, 211-213, 233-234, 269-272
- Evidence: Mixed concerns — this module pair logs via `print(...)` to stdout (ingest_raw) while ingest_worker uses `logging`. Multiple `except Exception: pass` / `return None` blocks mask the underlying error class: `_save_pdf_images` silently drops all images on any write error; `add_atom_from_insight` returns None for both LLM failures and disk errors with no log; `_resolve_reference_source` (155-156) swallows everything. These hide real bugs during a stability overhaul.
- Fix sketch: Route warnings through `logging` (module `_log`); narrow the broad excepts to the expected types (OSError, LLMError, ValueError) and at minimum `_log.debug/warning` the masked exception.
- Blast radius: Observability only; behavior preserved. Touches many small sites.
- Suggested PR: chore/ingest-logging-and-narrow-excepts

### [G01-ingest-core-9] (g) S3 — `_auto_discover_pending` calls `add_file` (which parses) per discovered file in a tight loop with no batching
- Loc: backend/src/curator/ingest_llm.py:300-317
- Evidence: For every untracked file under every raw_dir it calls `ingest_raw.add_file`, which opens a fresh `db.connect()` (running `SCHEMA_SQL` + `_apply_migrations` each time, per connect() at db.py:1262-1263) and fully parses the document. On a large vault re-scan this is O(files) connections each re-running schema/migration scripts, plus a full parse even for files that will dedup. The orphan-pruning above it also opens two separate connections.
- Fix sketch: Hold a single connection for the discovery pass, or short-circuit parse with a cheap content-hash/mtime check before full `parsers.parse`. At minimum, `_apply_migrations`-per-connect is a hot-path cost worth measuring.
- Blast radius: `wiki add`/`wiki update` auto-discovery latency on large vaults.
- Suggested PR: perf/auto-discover-batching

### [G01-ingest-core-10] (b/e) S3 — `generate_l1_summary` (LLM L1 path) is largely a parallel reimplementation of the structural L1 path and is gated off by default (`instant_l1=True`)
- Loc: backend/src/curator/ingest_raw.py:1531-1792
- Evidence: When `llm.instant_l1` is truthy (default `True`, line 1548) the function immediately delegates to `register_and_generate_l1`; the remaining ~240 lines (vision description, chunking, summary aggregation, manual frontmatter string-building at 1745-1765) are the legacy LLM-summary path. It duplicates frontmatter/page assembly that `_build_structural_context_page` does with proper `yaml.safe_dump`, here via raw f-string interpolation (e.g. `domain: "{domain or 'general'}"` at 1753 — unescaped, can break YAML if `domain` contains a quote). It is reachable only when a user flips `instant_l1` off.
- Fix sketch: Confirm whether the LLM-L1 path is still a supported mode (docs check). If yes, replace the hand-rolled frontmatter with the yaml-based builder and share the vision/chunk helpers; if deprecated, remove it. Either way the unescaped YAML interpolation is a latent corruption risk.
- Blast radius: Only the non-default `instant_l1=false` mode; YAML corruption on odd domain/tag values.
- Suggested PR: fix/l1-summary-yaml-and-dedupe

### [G01-ingest-core-11] (a) S3 — `on_error` writes a STATUS value into the `phase` column
- Loc: backend/src/curator/ingest_worker.py:89-90
- Evidence: `WorkerCallbacks.on_error` calls `db.update_job_progress(..., phase=consts.STATUS_ERROR)` — it stuffs the job *state* token `"error"` into the free-text `phase` label, but never transitions the job's `state` column to failed. Since this callback is also currently never invoked (see finding 2), it is doubly inert, but if callbacks are wired up it would mislabel rather than mark failure. The real failure handling lives in the `except` block at 253-267.
- Fix sketch: Either drop `on_error` or have it call the proper failure transition; do not overload `phase` with a state value.
- Blast radius: Dashboard phase label only (and only if callbacks become live).
- Suggested PR: fix/ingest-callbacks-wiring (bundle)

### [G01-ingest-core-12] (h) S3 — `run_l1_to_l3` continues after non-Ollama compile errors but still runs global L3 and marks ledger as fully built
- Loc: backend/src/curator/ingest_llm.py:542-578
- Evidence: The per-source loop only `break`s when `"Ollama" in cr.error` (564-565). For any other compile error it records the error in the IngestResult but keeps iterating, then unconditionally runs `compile_global_l3`, rebuilds the index, and writes ledger/overview (570-577) as if the run completed. A partial/failed multi-source build thus produces a "successful-looking" ledger and L3 set computed over an incomplete atom population, with no aggregate error surfaced to the caller beyond per-result `error` fields.
- Fix sketch: Decide failure policy — either abort global L3 when any source errored, or clearly propagate an aggregate "partial" status; the Ollama-only break is an ad-hoc special case.
- Blast radius: `wiki update`/`wiki build` full-pipeline runs with mixed success; misleading completion state.
- Suggested PR: fix/l1-to-l3-partial-failure-policy

## Positives (keep / do-not-break)
- `_apply_vlm_pdf_extraction` (ingest_raw.py:1428-1508) correctly keeps ALL DB access on the main thread (serial cache read → concurrent transcription with no DB in workers → serial cache write) and only parallelizes HTTP-based vision clients (`supports_concurrent_calls`), running agentic CLI clients serially. This is a well-reasoned SQLite-safety + rate-limit design; do not naively "optimize" it into worker-thread DB writes.
- Atomic file writes via temp-then-`replace` in `IngestWorker._write_dashboard` (worker.py:356-358) and `_write_build_canvas` (445-450) — prevents partial/corrupt dashboard/canvas reads by Obsidian. Preserve this pattern.
- `claim_next_job` uses `BEGIN IMMEDIATE` for atomic claim, and `recover_stale_jobs` re-queues `running` jobs on restart (worker.run calls it first) — solid crash-recovery design.
- Content-hash dedup in `add_file` (ingest_raw.py:1871-1909): unchanged content short-circuits, changed content correctly resets all layer statuses to pending and clears `context_id`. Reference-stub reuse via `_find_existing_reference_stub` correctly avoids duplicate `<name>-2.md` after a DB rebuild.
- `_chunk_text` (ingest_raw.py:580-658) carefully avoids splitting `$$...$$` and ``` blocks and guarantees forward progress — preserves math/code recall. The recursive `_summarize_chunk_with_fallback` (depth-bounded re-chunking) is a thoughtful resilience mechanism.
- Path-safety guards (`_safe_relative_path`, `_is_inside`, `_safe_vault_subdir`, the "refusing to import from .curator/Collections" checks in `safe_import_destination`) consistently prevent writes outside the vault and into the machine space — keep all of these.

## Open questions for the human
- Is `llm.instant_l1=false` (the legacy LLM-summary L1 path, ingest_raw.py:1531-1792) still a supported/documented mode, or can finding 10's ~240 lines be removed entirely?
- Should the rich `IngestCallbacks` progress surface (finding 2) be wired into the v0.3.1 compile pipeline for accurate dashboard progress, or formally removed? This is a product decision about how granular the build dashboard should be.
- For finding 1, is the intended cascade behavior "hard delete everything for the source" (mirror `_auto_discover_pending`) or "block deletion while a build is in flight"? Confirm before adding cascades vs. guards.
- `dag_edges`, `ingest_runs`, `source_pages` lack `ON DELETE CASCADE` while `source_pdf_pages` has it — was the inconsistency intentional, or should a migration normalize the FK actions?

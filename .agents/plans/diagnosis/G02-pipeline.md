# Diagnosis: G02-pipeline

Coverage: Read ALL target files completely —
`backend/src/curator/pipeline/{__init__,source_spans,knowledge_units,synthesis,memory_paths,projection,graph_index,community_reports,formula_recovery}.py` (read in full),
`claim_support.py` (697 lines, full), `compile.py` (647 lines, full, in two chunks).
Cross-checked neighboring `backend/src/curator/db.py` for the contracts these files depend on:
`upsert_knowledge_unit` (no `conn` param), `list_serving_units`, `list_generation_units`,
`get_authoritative_generation`, `relation_neighborhood`, `refresh_support_freshness`,
`create_compiler_generation`. Read CLAUDE.md project contract for spec/architecture context.

## Findings

### [G02-pipeline-1] (a) S2 — `extract_knowledge_units` batcher can emit a single batch that exceeds `max_chars`
- Loc: backend/src/curator/pipeline/knowledge_units.py:87-93
- Evidence: The batch-accumulation loop only splits when `current_batch` is non-empty
  (`if current_batch and current_chars + span_len > max_chars`). When a single span's
  `span_len` already exceeds `max_chars`, it is still appended as the first item of an
  otherwise-empty batch and shipped to the LLM whole. The preceding refine step (lines 61-76)
  only subdivides spans whose `span_len > max_chars`, but it uses `_chunk_text(text,
  chunk_size=max_chars - 500, overlap=500)`; a sub-chunk text of `max_chars-500` chars plus the
  id + `" (Part N)"` title + 50 overhead can still push `span_len` back over `max_chars`. So an
  oversized prose span can produce a batch the provider rejects (context overflow), which surfaces
  as an opaque "knowledge unit extraction failed" with no per-batch isolation.
- Fix sketch: After computing `span_len` in the batch loop, if `span_len > max_chars` AND
  `current_batch` is empty, still flush it as its own singleton batch but log/track it; better,
  make the refine `chunk_size` account for the id+title+overhead budget (`max_chars - 500 - len(id)
  - len(title) - 60`) so a refined sub-span is guaranteed to fit.
- Blast radius: L2 extraction for sources with very large single paragraphs/sections; failure is
  contained to that source's compile (returns error result) but blocks all its atoms.
- Suggested PR: "fix(pipeline): guarantee refined knowledge-unit sub-spans fit the LLM budget"

### [G02-pipeline-2] (b) S3 — Dead `rel_by_pair` dict in `detect_communities`
- Loc: backend/src/curator/pipeline/community_reports.py:71-75
- Evidence: `rel_by_pair: dict[str, list[str]]` is created and populated via
  `rel_by_pair.setdefault(uf.find(a), [])` inside the union loop, but it is never read anywhere
  afterward. The actual relation grouping is recomputed independently into `comp_relations`
  (lines 79-85). The `setdefault` also keys on `uf.find(a)` mid-union (before all unions complete),
  so its keys would be stale even if used. Pure dead code with a misleading comment
  ("# ensure key exists later").
- Fix sketch: Delete the `rel_by_pair` declaration and the `setdefault` line.
- Blast radius: None functionally; cleanup only. (Per CLAUDE.md "mention; don't delete pre-existing
  dead code" — flagging, not fixing.)
- Suggested PR: "chore(pipeline): drop unused rel_by_pair in detect_communities"

### [G02-pipeline-3] (g) S2 — N+1 DB connections in `compile_source_l2` post-publish re-upsert
- Loc: backend/src/curator/pipeline/compile.py:319-347 (and validation loop 268-269)
- Evidence: After publish, the loop over `units` calls `db.upsert_knowledge_unit(...)` once per unit
  (line 323) and `db.record_artifact_dependency(...)` + `db.insert_dag_edge(...)` per span per unit
  (lines 338-347). Each of those db helpers opens its OWN `connect(db_path)` (verified:
  `upsert_knowledge_unit` at db.py:2148 opens a fresh connection, takes no `conn`). For a source
  with hundreds of units each citing several spans this is hundreds–thousands of separate SQLite
  connections/transactions. The earlier per-unit `validate_claim_support` loop (line 268-269) is
  similarly per-unit, each opening multiple connections internally.
- Fix sketch: Wrap the post-publish re-emit writes in a single `db.connect()` transaction and thread
  `conn` through `upsert_knowledge_unit`/`record_artifact_dependency`/`insert_dag_edge` (most sibling
  helpers already accept `conn`; `upsert_knowledge_unit` notably does NOT — see finding 4).
- Blast radius: Performance only on large sources; correctness unaffected. Hot path of `wiki build`.
- Suggested PR: "perf(pipeline): batch post-publish atom re-emit writes into one transaction"

### [G02-pipeline-4] (a) S2 — Post-publish `upsert_knowledge_unit` re-write is redundant and cannot join the publish transaction
- Loc: backend/src/curator/pipeline/compile.py:323-335
- Evidence: Immediately after publishing, each serving unit is re-`upsert`ed by `unit_id` solely to
  stamp `atom_node_id=atom_id`. The unit row already exists and was just published; the only new
  data is `atom_node_id`. `db.upsert_knowledge_unit` (db.py:2130) accepts no `conn` parameter, so
  this write happens on a separate connection AFTER the atomic publish transaction has committed —
  i.e. it is outside the publish gate's atomicity guarantee. If the process dies between
  `_publish_generation` (line 300, committed) and these writes, the generation is authoritative but
  its units have no `atom_node_id` and the ATM markdown files on disk may be orphaned/regenerated
  with fresh ids on the next `reemit_projections` (which calls `unit.get("atom_node_id") or new_atom_id()`).
- Fix sketch: Either persist `atom_node_id` inside the publish transaction (add `conn` support to
  `upsert_knowledge_unit` or a narrow `set_atom_node_id(conn=...)` helper), or accept it is a derived
  projection detail and document the recovery path. The full re-upsert of all 12 columns just to set
  one field is also over-broad — use a targeted UPDATE.
- Blast radius: Crash-window partial-write risk; atom_node_id stability across reemit. `wiki build` /
  `wiki sync reemit`.
- Suggested PR: "fix(pipeline): set atom_node_id inside the publish transaction"

### [G02-pipeline-5] (h) S2 — `reemit_projections` mints NEW concept ids on every call (projection id churn)
- Loc: backend/src/curator/pipeline/compile.py:637-642; backend/src/curator/pipeline/synthesis.py:150-152
- Evidence: In `reemit_projections`, concept pages are written as
  `concept_id = projection.new_concept_id()` (a fresh `CON-<uuid>`) for every report on every reemit,
  and the old `CON-*.md` files are deleted first (line 623). There is no `community_report` column
  storing a stable concept id (unlike atoms, which reuse `unit.get("atom_node_id")` at line 632). So
  every `wiki sync`/reemit reassigns brand-new CON ids to the same concepts, breaking any wikilink or
  cross-reference that pointed at a prior CON id. (Synthesis SYN ids ARE stable — they are the DB
  `node['id']`, see synthesis.py:152 — so the inconsistency is concept-only.)
- Fix sketch: Persist a stable concept id on the `community_reports` row (mirroring `atom_node_id`),
  or derive the CON id deterministically from `community_key`, and reuse it on reemit instead of
  `new_concept_id()`.
- Blast radius: Any feature linking to CON pages (search index doc ids, plugin links, ledger refs)
  sees ids change under it. `wiki sync`, `reemit_projections`, search materialization.
- Suggested PR: "fix(pipeline): stable concept ids across projection reemit"

### [G02-pipeline-6] (c) S2 — `compile_global_l3` swallows per-report prose errors then aborts synthesis silently
- Loc: backend/src/curator/pipeline/compile.py:562-601
- Evidence: The prose loop catches every exception per report into `errors` (line 576-577) and keeps
  going, but a single failed report poisons the whole run: synthesis is skipped (`if not errors`,
  line 581), ALL L2-done sources are marked `l3` = "error" (lines 594-598), and the function raises
  at the end (line 601). So one transient LLM failure on one community discards the prose of all the
  reports that DID succeed (their CON pages were already written to disk at lines 573-574 but the
  source statuses are flipped to error, and synthesis never runs). The partial CON files on disk are
  now inconsistent with the error status. Also the broad `except Exception` masks the failure type
  (only `str(e)` is kept), making diagnosis hard.
- Fix sketch: Decide a policy: either fail fast on the first report error (don't write partial CON
  pages), or treat per-report failures as non-fatal and still run synthesis over the reports that
  succeeded. At minimum, don't mark sources whose reports all succeeded as l3=error because an
  unrelated community failed.
- Blast radius: L3 robustness; a flaky provider on one community blocks the entire L3/L4 layer and
  leaves disk/DB status inconsistent. `wiki build` global phase.
- Suggested PR: "fix(pipeline): isolate per-community-report failures in compile_global_l3"

### [G02-pipeline-7] (g) S3 — `build_memory_paths` walk: N+1 `relation_neighborhood` + uncached `_domain_fit` entity fetches
- Loc: backend/src/curator/pipeline/memory_paths.py:70-101
- Evidence: `_walk` calls `db.relation_neighborhood(db_path, [current])` for every visited node
  (db.py:3251 opens a connection per call), and `_domain_fit` (lines 61-68) calls
  `db.get_graph_entity` for BOTH endpoints of every hop with no cache, so the same entity is
  re-fetched on every path that touches it. For a dense graph this is a connection storm. Also the
  `if len(paths) >= max_paths` cap is only checked at `_walk` entry, so a single node with many
  neighbors can append far past `max_paths` before the next recursion checks (then the result is
  sliced at line 107 — correctness is fine, but wasted scoring work).
- Fix sketch: Open one connection for the whole walk (thread `conn` through `relation_neighborhood`,
  which currently lacks a `conn` param), and memoize `_domain_fit` per entity id. Re-check the
  `max_paths` cap inside the neighbor loop.
- Blast radius: Performance of the `explore` retrieval route only; no correctness impact.
- Suggested PR: "perf(pipeline): single-connection memory-path walk with domain-fit cache"

### [G02-pipeline-8] (a) S3 — `spans_from_sections` page-number parse drops/coerces non-digit pages and float pages
- Loc: backend/src/curator/pipeline/source_spans.py:94
- Evidence: `page_number = int(page) if isinstance(page, (int, str)) and str(page).isdigit() else None`.
  A `bool` is an `int` subclass so `page=True` would pass `isinstance(..., int)` and `str(True)` is
  `"True"` → `.isdigit()` False → None (harmless). But a legitimate float page (e.g. parser emits
  `page=12.0`) fails `isinstance(page, (int,str))`-True yet `str(12.0)="12.0"`.isdigit() is False, so
  the page is silently dropped to None, losing provenance. A negative page string "-3" also → None.
- Fix sketch: Normalize via `int(float(page))` inside a try/except for numeric-ish inputs, or have the
  parser layer guarantee int pages and assert it.
- Blast radius: Citation page-number provenance fidelity for parsers that emit float/locator pages.
  Low frequency; affects display/citation only.
- Suggested PR: "fix(pipeline): robust page-number coercion in spans_from_sections"

### [G02-pipeline-9] (e) S3 — `compile.py` is a god-module mixing six responsibilities behind one public surface
- Loc: backend/src/curator/pipeline/compile.py:1-648 (esp. `__all__` lines 47-56)
- Evidence: One 648-line module owns: (1) source re-parse/section extraction, (2) full-span hydration
  (`hydrate_span_text`/`hydrate_spans`/`SpanTextUnavailable`), (3) L2 orchestration with staged
  publish, (4) the generation lifecycle primitives (`_run_publish_gate`, `_discard_staged_units`,
  `_retire_prior_generation_units`, `_publish_generation`, `recompile_source`), (5) L3 global
  orchestration, and (6) projection reemit. Its `__all__` even re-exports the entire claim_support
  and formula_recovery surfaces (lines 49-51) purely as a façade, creating tight import coupling —
  callers import everything-Plan-B from `compile`. Hydration in particular has no dependency on
  compile orchestration and belongs beside `source_spans`.
- Fix sketch: Extract hydration into a `span_hydration.py`, extract the generation/publish primitives
  into a `generations.py`, and drop the pass-through re-exports (let callers import from the owning
  module). Keep `compile.py` as the orchestrator only.
- Blast radius: Refactor-time only; wide import surface means many call sites reference these names —
  do it with care and keep a deprecation shim or update imports atomically.
- Suggested PR: "refactor(pipeline): split hydration + generation lifecycle out of compile.py"

### [G02-pipeline-10] (h) S3 — `recover_formula` writes the candidate, then re-validates in a SEPARATE transaction (partial-write window)
- Loc: backend/src/curator/pipeline/formula_recovery.py:161-228
- Evidence: The reviewed-candidate path persists the candidate metadata in one `db.connect()` block
  (lines 161-176), then opens a second connection to re-hydrate sibling recovered formulas (190-208),
  then calls `validate_claim_support` (its own connection) and `upsert_claim_support` /
  `set_unit_formula_status` (more connections). The candidate is already written as `status:"reviewed"`
  before validation runs; if the process dies after line 176 but before line 228, the span metadata
  records a `reviewed` candidate while the unit's `formula_status` is still `uncertain` and no
  `formula` claim_support row exists — a durable inconsistency that `run_compiler_audit`'s formula
  consistency check (claim_support.py:530-535) is designed to flag, but the unit silently stays
  `uncertain` rather than rolling the candidate back.
- Fix sketch: Defer writing `status:"reviewed"` until after validation succeeds, or do the metadata
  write + support upsert + status flip in a single transaction (thread one `conn` through the
  `db.*` helpers, which mostly accept `conn`). `validate_claim_support` already accepts `conn`.
- Blast radius: Formula-recovery durability under crash/interrupt; rare but produces audit-visible
  inconsistency. P5 recovery lifecycle.
- Suggested PR: "fix(pipeline): make reviewed-formula recovery atomic"

### [G02-pipeline-11] (b) S3 — Duplicated chunk-batching logic across `knowledge_units` and `graph_index`
- Loc: backend/src/curator/pipeline/knowledge_units.py:54-96 and backend/src/curator/pipeline/graph_index.py:77-115
- Evidence: Both modules independently implement the same pattern: `try: max_chars =
  int(client.optimal_chunk_chars()) except Exception: max_chars = 60000`, an oversized-item refine
  pass, and the identical greedy `current_batch`/`current_chars` accumulation loop with the same
  `if current_batch and current_chars + len > max_chars` condition. The estimation overhead constants
  (`+50`, `+30`) and the `60000` fallback are copy-pasted. Any fix to the batching bug in finding 1
  must be applied in two places, which is exactly how such bugs diverge.
- Fix sketch: Extract a shared `_batch_by_chars(items, *, size_of, max_chars, refine=...)` helper into
  a small `pipeline/_batching.py` and have both extractors call it.
- Blast radius: Refactor-time; reduces drift risk between the two LLM batchers.
- Suggested PR: "refactor(pipeline): share LLM chunk-batching between L2 and graph extraction"

### [G02-pipeline-12] (c) S3 — `hydrate_spans` silently omits drifted/unreadable spans with a bare `except Exception: continue`
- Loc: backend/src/curator/pipeline/compile.py:184-192
- Evidence: `try: index = _reparse_hash_index(...) except Exception: continue` swallows ALL exceptions
  (not just missing-file / parse errors) and silently drops every span of that source from the output.
  The single-span sibling `hydrate_span_text` correctly raises `SpanTextUnavailable` with a reason;
  the batch path gives the caller no signal about WHY spans are missing (unreadable source vs. real
  drift vs. an unexpected bug). The docstring claims callers "flag them stale/unavailable" but the
  caller can't distinguish a transient IO error from genuine content drift.
- Fix sketch: Catch the narrow expected exceptions only (and let truly unexpected ones propagate), or
  return per-span failure reasons alongside the successes so the caller can flag them precisely.
- Blast radius: Evidence-surface accuracy (F10 hydration). Masks bugs in parse/re-derive path.
- Suggested PR: "fix(pipeline): narrow hydrate_spans exception handling + surface failure reasons"

### [G02-pipeline-13] (h) S3 — `_domain_fit` returns 0.0 for missing/no-term entities, indistinguishable from "no match"
- Loc: backend/src/curator/pipeline/memory_paths.py:61-68, 92
- Evidence: `_domain_fit` returns `0.0` both when there are no `domain_terms` AND when the entity is
  missing AND when it simply doesn't match. The hop's domain_fit is `max(_domain_fit(current),
  _domain_fit(nxt))` — so a dangling relation pointing at a deleted entity scores identically to a
  legitimate non-matching one. This is minor for scoring, but a relation whose endpoint entity row no
  longer exists (`get_graph_entity` → None) is silently treated as a valid hop, so the walk can build
  paths through tombstoned/deleted entities.
- Fix sketch: When `db.get_graph_entity` returns None for a hop endpoint, skip the hop (it's a
  dangling relation) rather than scoring it 0.0 and continuing the walk through it.
- Blast radius: `explore` route path quality; could surface paths citing nonexistent entities.
- Suggested PR: "fix(pipeline): skip memory-path hops through missing entities"

## Positives (keep / do-not-break)
- The copy-on-stage / atomic-publish design in `compile_source_l2` and `recompile_source`
  (compile.py:251-311, 460-527) is genuinely careful: graph LLM extraction runs IN MEMORY during
  staging (`extract_graph_data`) and persistence is deferred into the SAME publish transaction as
  reconcile + flip, so a graph failure occurs behind the gate and never leaves a published generation
  without its graph. The single-transaction `conn` threading through reconcile/persist/publish is the
  right shape — do not "simplify" it back into separate transactions.
- `claim_support.validate_claim_support` trichotomy (verified/failed/uncertain) and the ordered
  formula-token subsequence matcher (`_formula_tokens` + `_is_formula_subsequence`) correctly preserve
  operation direction/grouping (`a^b != b^a`). This is the core soundness gate — preserve its exact
  thresholds and ordering semantics.
- `recover_formula` and `invalidate_formula_recoveries` use deliberate read-modify-write-in-one-
  transaction for span metadata to prevent TOCTOU (formula_recovery.py:161-176, 240-284) — keep that
  pattern (note finding 10 is about the cross-transaction tail, not this guarded core).
- Content-addressed `dependency_hash` / `corpus_dependency_hash` skip-when-unchanged logic
  (synthesis.py:79-82, community_reports.py:101-133) avoids needless LLM calls — preserve.
- `_UnionFind` with path compression (community_reports.py:35-51) is correct and deterministic;
  `detect_communities` output is sorted for stable community keys.
- `hydrate_span_text` verifies re-derived text against the stored `content_hash` and refuses to
  substitute the 200-char preview — this is the verification key for F10; do not weaken it.
- SQLite variable-cap chunking (`_SQL_VAR_CHUNK = 900`, compile.py:155-178) correctly guards bulk
  `IN (...)` queries against SQLITE_MAX_VARIABLE_NUMBER.

## Open questions for the human
- Finding 5 (CON id churn): is concept-page id stability a real requirement, or are CON ids treated
  as fully ephemeral search-doc ids that nothing links to durably? If the latter, finding 5 is a
  non-issue; if anything (plugin, ledger, wikilinks) references CON ids, it is an S2 bug.
- Finding 6: what is the intended L3 failure policy — fail-fast on the first community-report error,
  or best-effort (succeed on the reports that worked and still run synthesis)? The current behavior is
  a mix (writes partial CON pages, then aborts) that seems unintended.
- Finding 4: is `atom_node_id` considered durable provenance (must survive a crash mid-build) or a
  disposable projection detail that any reemit may reassign? That determines whether the post-publish
  re-upsert must join the publish transaction.
- `recompile_source` (the no-LLM DB-level republish) re-runs `validate_claim_support` on all active
  units each call; for an unchanged source this is gated out earlier by the content_hash short-circuit
  (compile.py:481-487), but is there a path where a large source republishes frequently and pays this
  full re-validation cost? Worth confirming against the `wiki sync` cadence.

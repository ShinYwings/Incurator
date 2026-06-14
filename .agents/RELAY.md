# Cross-Agent Relay State

## Status: P5 COMPLETE (uncommitted, awaiting Gemini review) — next action is P6 (claim-grounded reports + reconciliation); P7 owns the remaining graph_audit reds

**Branch:** `feature/plan-c-graph-quality`
**Target Plan:** `.agents/plans/C_graph_quality.md`

## Goal
Implement Batch 2: Plan C (Graph Quality) to stabilize the graph layer, establish community reports, and synthesize insights. The previous milestone (Plan B) has been successfully merged and shipped.

## Immediate Next Action
**Gemini: review the uncommitted P5 `db.connected_components` implementation** (the
filtered-connected-components hierarchy fallback). Then proceed to **P6 — claim-
grounded reports + precise reconciliation** (plan §342–358). P0–P5 are complete; the
only remaining Plan C reds are the 4 `test_plan_c_hierarchy_audit.py` `graph_audit`
tests (owned by **P7**, alongside the testbed + `wiki lint` graph-audit wiring) and
the 4 docs-first `test_spec_sync` version-gate reds (resolve at P10).

Pinned hooks still to land in later phases (refinable when turning green):
- `db.graph_audit(db_path) -> list[dict]` (**P7**) — each violation has `code` +
  offending `subject_id`; empty list == clean (flags active-without-≥2-lineages,
  redirected-endpoint reference, quarantined-missing-reason,
  report-finding-without-active-support). The 4 reds are written and red.
- P6 reconciliation/report hooks (`db.rebuild_graph_generation` no-amplification,
  `reconcile_source_change` downstream closure, claim-grounded report generation
  with no broad-span fallback) — gold fixtures still to be written (P2 "remaining
  work").

Hierarchy selection is benchmark-driven (§27.4): seeded weighted Leiden is a
CANDIDATE, filtered connected components the degraded fallback. Leiden adoption
stays BLOCKED — the P7/GQ07 handoff proved production relation confidence is
non-discriminative (no labeled relation-quality data exists to justify a different
partition), so `connected_components` is the selected shipped implementation. The
community-identity columns (`parent_community_key`, `config_hash`, `member_hash`,
`support_hash`, `retired_at`) ALREADY EXIST from P3's migration — P5 is logic, no
new migration.

## Progress Status
- Workspace prepared: `master` pulled, `feature/plan-c-graph-quality` branched
  (sits exactly at merged-B `master` `bcfb36a`; no own commits before P0).
- **P0 COMPLETE** (2026-06-14, Claude): coding-time Evidence Ledger
  `.agents/plans/C_roadmap_evidence.md` written. Captured rollback anchor
  (SHA, schema v8→9 plan, versions, active scenario `gaussian_splatting`,
  authoritative generations GEN-bc1dc52a/GEN-57bd7593). DB backed up
  (`state.sqlite.C-baseline.bak`, integrity ok, restore parity verified).
  Read-only graph baseline audit recorded; concerns reproduced/scheduled
  (live unsupported-relation `REL-b6d5b9fc`; GQ07 confidence-calibration
  scheduled for P2/P4). Multi-metric hierarchy benchmark contract frozen.
  No behavior change.

## P1 Schema Correction (2026-06-14, Claude — user-directed)
User identified TWO critical flaws in the frozen P1 schema and directed the fix
before P2. Both corrected in `SCHEMA.md` §21 + `SYSTEM_BEHAVIOR.md` §27 (+ synced
`WORKFLOW_GUIDE`/`_KR`). DDL re-validated in sqlite; no production code touched.

1. **`entity_aliases` surrogate key (homonym support).** Old PK
   `(alias_normalized, alias_display, resolution_status)` collapsed homonyms —
   a second entity claiming the same surface form collided and silently
   overwrote the first. Fix: PK is now the surrogate `id` (`ALI-<UUID8>`); a
   partial unique index `idx_entity_aliases_resolved (alias_normalized,
   entity_id, resolution_status) WHERE entity_id IS NOT NULL` keeps resolved
   rows deduped while allowing one surface form to resolve to MANY distinct
   entities. SCHEMA §21.1 + SYSTEM_BEHAVIOR §27.1.
2. **No `duplicate_proposition` quarantine reason (support aggregation).** A
   relation's identity IS its canonical proposition `(resolved src, resolved
   tgt, relation_type)`; re-assertion AGGREGATES independent support onto the
   one relation (§21.5), so there is no duplicate row to quarantine — and
   quarantining one would suppress its support and corrupt the independent
   count. Removed the code from the frozen set (now 6: `unsupported`,
   `self_loop`, `contradiction`, `copied_source_only`, `bridge_risk`,
   `endpoint_unresolved`). An edge is either `unsupported` or valid with
   aggregated support. SCHEMA §21.5/§21.6 + SYSTEM_BEHAVIOR §27.2/§27.3.

## P3 COMPLETE (2026-06-14, Claude) — v9 migration foundation + resolution lifecycle
Implemented the additive v9 migration foundation and the entity-resolution /
reversible-merge API. **19 P3 gold tests now green** (11 `test_plan_c_resolution.py`
+ 8 of 9 `test_plan_c_graph_quality.py`; the 9th needs the P4
`QUARANTINE_REASON_CODES` constant and stays red by design). Full suite:
**844 passed, 17 failed, 8 xfailed** (was 824 passed at P2; +20 green = 19 in-scope
P3 + 1 incidental `test_plan_c_relation_topology` edge-class test the new
`edge_class` column satisfied). `ruff check src/` clean; `mypy src/` adds **0** new
errors (the 1 reported db.py `lastrowid` error is pre-existing, present at HEAD).
**Not committed** — per the wake instruction, stopped after turning P3 green and
updating this relay; the implementer/user owns the commit.

The 17 remaining reds are all out of P3 scope: 13 later-phase Plan C reds (1
graph_quality P4 `QUARANTINE_REASON_CODES`; 6 `relation_topology` P4 lifecycle; 6
`hierarchy_audit` P5/P7) + the 4 pre-existing `test_spec_sync` docs-first version
gate (resolves at P10).

- **db.py — migration foundation (`SCHEMA_VERSION` 8 → 9, additive/idempotent):**
  - Base `SCHEMA_SQL` + idempotent `_migrate_v9_graph_quality` create the four new
    tables (`entity_aliases` surrogate-`id` PK with the partial unique
    `idx_entity_aliases_resolved` WHERE `entity_id IS NOT NULL`,
    `entity_merge_proposals`, `entity_resolution_lineage`, `graph_relation_supports`)
    and add the §21.4/§21.6/§21.7 columns to `graph_entities` /`graph_relations` /
    `community_reports`. Backfill infers nothing (legacy entities `canonical`;
    legacy relations `provisional`/`extracted`/no generation; zero alias/support rows).
  - Indexes on NEW columns of EXISTING tables (`idx_graph_relations_lifecycle`,
    `idx_community_reports_parent`) live in the migration (created AFTER the ALTER),
    NOT in `SCHEMA_SQL` — same old-DB ordering convention the v8 `knowledge_units`
    indexes follow, else `executescript` fails on a pre-v9 DB.
  - Extended the `deleted_records` CHECK list (base + migration rebuild) with the
    four new tables.
- **db.py — P3 resolution API (SCHEMA §21.1–§21.4 / SYSTEM_BEHAVIOR §27.1):**
  - `RESOLUTION_STATUS_CODES`, `MERGE_DECISION_CODES` frozensets.
  - `evaluate_merge_guards(...)` — read-only; returns the four §27.1 guard booleans
    + `verdict`: avoid_merges → `rejected`; all-four-pass → `accept`; any other guard
    failure → `ambiguous_candidate` (similarity only PROPOSES, never auto-fuses).
  - `propose_entity_merge` (DEC- row, never rewrites graph) / `accept_entity_merge`
    (redirects origin, re-points relation endpoints onto survivor, writes reversible
    `entity_resolution_lineage.rewrite_json`) / `reverse_entity_merge` (replays
    lineage in reverse → byte-identical pre-merge endpoints, decision kept as audit).
- **db_sync.py:** wired the four new tables into `SYNC_TABLES` / `_PK_COL` /
  `_UPDATED_AT_COL` (aliases/proposals = `id` PK; lineage/supports = composite PK,
  always-upsert; lineage has no `updated_at`) for export/import round-trip (§27.7.4).
- **Consequential test updates (SCHEMA_VERSION bump fallout, NOT P3 gold tests):**
  the v8-pinned schema-version assertions in `test_db_schema.py`, `test_db_sync.py`,
  `test_plan_b_compiler.py`, `test_plan_b_migration.py` were re-pointed at
  `db.SCHEMA_VERSION` (robust across future additive bumps). Re-pinned `db.py`'s hash
  in `docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml` `evaluated_code.file_sha256` —
  the established Plan B precedent (commit `225b841`) for re-anchoring the D2 frozen
  evidence when a milestone legitimately edits db.py; the v9 changes are purely
  additive so the frozen D2 metrics are unaffected by construction.
- **Pre-existing latent lint (left untouched, surgical rule):** `tests/test_db_sync.py`
  has 2 unused imports (`os`, `SYNC_TABLES`) flagged by ruff — present before this
  work, on import lines I did not touch, and outside CI's `ruff check src/` gate.

## P4 COMPLETE (2026-06-14, Claude) — relation lifecycle + quarantined topology
Implemented the P4 relation-support/quarantine compiler. **All 7 in-scope P4 gold
tests now green** (6 `test_plan_c_relation_topology.py` lifecycle/topology +
the 1 remaining `test_plan_c_graph_quality.py`
`test_duplicate_proposition_is_not_a_quarantine_reason`;
`test_edge_class_separates_authored_from_extracted` was already green from P3's
`edge_class` column). Full suite: **851 passed, 10 failed, 8 xfailed** (was 844
passed at P3; +7 in-scope greens). `ruff check src/` clean; `mypy src/` adds **0**
new errors (the 1 db.py `lastrowid` error at line 1353 is pre-existing, present at
HEAD). **Committed `29b3ded`** (2026-06-14, Claude) after Gemini's P4 approval —
`feat(core): implement P4 relation lifecycle + quarantined topology`.

The 10 remaining reds are all out of P4 scope: 6 `test_plan_c_hierarchy_audit.py`
(P5 `connected_components` + P7 `graph_audit`) + the 4 `test_spec_sync` docs-first
version gate (resolves at P10). No new migration — P4 is logic-only on columns P3
already added.

## P5 COMPLETE (2026-06-14, Claude) — filtered connected-components hierarchy fallback
Implemented the P5 deterministic community-construction fallback. **Both in-scope P5
gold tests now green** (`test_connected_components_baseline_excludes_quarantined_bridge`
+ `test_retired_relation_is_excluded_from_active_topology` in
`test_plan_c_hierarchy_audit.py`). Full suite: **853 passed, 8 failed, 8 xfailed**
(was 851 passed at P4; +2 in-scope P5 greens). `ruff check src/` clean; `mypy src/`
adds **0** new errors (the 1 db.py `lastrowid` error at line 1353 is pre-existing).
**Not committed** — per the wake instruction, stopped after turning P5 green and
updating this relay so Gemini can review; the implementer/user owns the commit. P4
(`29b3ded`) IS committed; the uncommitted worktree is P5 only.

The 8 remaining reds are all out of P5 scope: 4 `test_plan_c_hierarchy_audit.py`
`graph_audit` tests (**P7**) + the 4 `test_spec_sync` docs-first version gate
(resolves at P10). No new migration — P5 is logic-only on existing columns.

- **db.py — `connected_components(db_path, *, only_active=True, conn=None) ->
  list[set[str]]`** (SYSTEM_BEHAVIOR §27.4, Arena decision 10): the EXPLICIT
  degraded hierarchy fallback. Nodes = `canonical` (§27.1) entities; edges =
  non-self-loop relations between two canonical endpoints. `only_active=True`
  (default) restricts edges to `lifecycle_status='active'` (§27.3), so a
  `quarantined` noisy bridge or `unsupported` edge cannot fuse two clusters into one
  giant component; `only_active=False` admits every non-`retired` relation
  (provisional + quarantined) for diagnostics. A `retired` tombstone (§27.8) is
  NEVER a topology input in either mode (its endpoints fall apart). An entity with
  no qualifying edge is its own singleton component. Union-find with path
  compression, rooted at the smaller id; output sorted by `(size, sorted members)`
  for full determinism — a fixed `(graph, config, seed)` yields an identical
  partition (§27.4). O(V+E·α). Placed under a new
  `# --- community construction (hierarchy fallback) ---` section in db.py.
- **No Leiden adopted.** Per §27.4 + the P7/GQ07 handoff, seeded weighted Leiden is
  a CANDIDATE blocked on labeled discriminative relation-quality data that does not
  exist (production confidence is non-discriminative). The multi-metric benchmark
  cannot currently justify adopting it without regression, so the degraded
  filtered-connected-components path is the SELECTED shipped implementation — no
  speculative untested partition code added (Simplicity First). The benchmark
  fixtures that would compare candidates remain P2 "remaining work".
- **`docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml`:** re-armed the db.py drift
  tripwire again — extended the `plan_c_rearm` narrative to cover P5 (now "across
  three phases") and re-pinned `file_sha256` db.py `47f5b267…` → `7a8555e6…`. The
  P5 change is additive graph-compiler logic touching NO retrieval/ranking/fusion/
  projection/embedding/chunking/materialize_chunks path the lexical Q06 holdout
  exercises, so the frozen Q06 metric is provably unaffected.
- **Docs:** no behavioral spec/guide drift — P5 implements exactly the frozen P1
  contract (SYSTEM_BEHAVIOR §27.4 authored at P1). `connected_components` is an
  internal DB helper (no new CLI/MCP/plugin surface), so guides stay in sync; the
  `wiki lint` graph-audit surface (§27.6) is P7 work.

- **db.py — P4 constants (SCHEMA §21.6):**
  - `QUARANTINE_REASON_CODES` — frozen 6-code set
    (`unsupported`, `self_loop`, `contradiction`, `copied_source_only`,
    `bridge_risk`, `endpoint_unresolved`); `duplicate_proposition` DELIBERATELY
    absent (Flaw 2 — re-assertion aggregates support, §21.5).
  - `_QUARANTINE_REEVAL_TRIGGERS` — every quarantine reason paired with its
    `reeval_trigger` (§21.6: quarantine is inspectable/re-evaluable, never an
    opaque discard).
  - `_RELATION_CORROBORATION_THRESHOLD = 2` (§21.5/§27.2 active floor).
- **db.py — `compile_relation_lifecycle(db_path, *, relation_id, bridge_risk_ids=
  None, conn=None) -> str`** (SCHEMA §21.5/§21.6, SYSTEM_BEHAVIOR §27.3): persists
  `lifecycle_status`/`quarantine_reason`/`reeval_trigger` and returns the status.
  Decision order = structural admissibility BEFORE support quality:
  (1) `self_loop` (src==tgt); (2) `endpoint_unresolved` (an endpoint's
  `resolution_state != 'canonical'`); (3) `contradiction` (a `contradicts` edge
  joins the endpoints, excluding self); (4) `bridge_risk` (relation ∈ the cut-edge
  set); (5) support corroboration over DISTINCT `verified` `source_lineage_hash` —
  0 → `unsupported`, exactly 1 → `copied_source_only`, ≥2 → `active`. `active`
  clears reason+trigger; quarantine sets both. The optional `bridge_risk_ids` lets a
  whole-generation compiler pass the topology once instead of recomputing per
  relation; standalone callers omit it and it's computed lazily only if the earlier
  checks didn't already decide. Helper `_classify_relation_lifecycle` returns the
  `(status, reason)` decision without writing.
- **db.py — `detect_bridge_risk_relations(db_path, *, conn=None) -> list[str]`**
  (SCHEMA §21.6 / §21.9 GQ07): PURELY TOPOLOGICAL cut-edge detection — iterative
  Tarjan bridge-finding over the undirected non-self-loop, non-retired relation
  graph (edge-index parent tracking so PARALLEL edges are never cut edges), gated by
  a density check (both sides of the cut ≥2 nodes, via DFS subtree sizes + a BFS
  component-size pass) so a lone edge between two singletons is NOT flagged. It does
  NOT threshold on `confidence` — GQ07 proved production confidence
  non-discriminative, so a raw-confidence filter is a rejected default; the gold
  fixture's equally-low-confidence intra-cluster chord (on a cycle, not a cut edge)
  is correctly NOT flagged, proving structure—not confidence—is the discriminator.
  Returns sorted relation ids. O(V+E).
- **db.py — import:** added `from collections import defaultdict, deque` (used by
  the bridge topology pass).
- **`docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml`:** re-armed the db.py drift
  tripwire — added a `plan_c_rearm` narrative block (the established Plan B
  governance pattern; P3's commit re-pinned the hash to `ab865daa` WITHOUT a
  narrative, now documented) and re-pinned `file_sha256` db.py
  `ab865daa…` → `47f5b267…`. The v9/P4 changes are additive entity/relation
  graph-compiler logic touching NO retrieval/ranking/fusion/projection/embedding/
  chunking/materialize_chunks path the lexical FTS5/BM25 Q06 holdout exercises, so
  the frozen Q06 metric is provably unaffected; the single-consumption harness
  (run_count=3, max) cannot regenerate it, so the fingerprint is a re-armable drift
  tripwire, not a permanent freeze.
- **Docs:** no behavioral spec/guide drift — P4 implements exactly the frozen P1
  docs-first contract (SCHEMA §21.5/§21.6, SYSTEM_BEHAVIOR §27.3 were authored at
  P1). No new CLI/MCP/plugin surface, so guides are already in sync.

## P2 COMPLETE (2026-06-14, Claude) — 33 failing gold tests verified
Four TDD-red modules now in place — **33 intended reds total, all verified red**.
All fail for the intended reason (v9 schema/columns/constants/API not built yet)
with intention-revealing messages — never via `ImportError`. Full suite after
this batch: **824 passed, 33 Plan C reds, 8 xfailed**; ruff clean on all four
modules; no legacy regression. Committed `0f173ec` (module 1) + the P2 batch.
P2 (TDD red gold tests) is finished; the only remaining Plan C work is
implementation, which begins at P3.

- `test_plan_c_graph_quality.py` (9) — v9 migration foundation + both corrected
  flaws: schema-version, new-table/column creation, infer-nothing backfill,
  homonym surrogate key, exact-dup rejection, support aggregation /
  independence-by-lineage, `duplicate_proposition`-absent contract.
- `test_plan_c_resolution.py` (11) — entity resolution adversarial fixtures:
  resolution/merge-decision frozen enums, synonyms (many surface→one entity),
  multilingual aliases, abbreviation homonym-risk stays ambiguous, type-conflict
  /`avoid_merges`/contradiction guards, ambiguous-alias non-resolution, accepted
  merge→redirect+lineage, and merge reversal (byte-identical restore).
- `test_plan_c_relation_topology.py` (7) — relation lifecycle: self_loop,
  unsupported, copied_source_only, endpoint_unresolved, fully-supported→active,
  noisy-bridge `bridge_risk` detection, authored-vs-extracted edge class.
- `test_plan_c_hierarchy_audit.py` (6) — connected-components baseline excludes a
  quarantined bridge; retired-tombstone excluded from active topology; graph
  audit flags (active-without-support, redirected-reference, quarantined-missing-
  reason, report-finding-without-active-support).

- **Pinned v9 API hooks the tests pin (the implementer must define these as the
  phases land; names are the proposed contract, refinable when turning green):**
  - Constants — `db.SCHEMA_VERSION == 9`; `db.QUARANTINE_REASON_CODES` (frozen
    6-code set, P4); `db.RESOLUTION_STATUS_CODES` (§21.1, P3);
    `db.MERGE_DECISION_CODES` (§21.2, P3).
  - P3 resolution — `db.evaluate_merge_guards(db_path, *, source_entity_id,
    target_entity_id, avoid_merges=()) -> Mapping` with the four §27.1 guard
    booleans (`type_match`, `context_overlap`, `no_contradiction`,
    `not_avoid_listed`) + `verdict ∈ {accept, ambiguous_candidate, rejected}`;
    `db.propose_entity_merge(... rationale, evidence) -> decision_id`;
    `db.accept_entity_merge(*, decision_id)`; `db.reverse_entity_merge(*,
    decision_id)`.
  - P4 relations — `db.compile_relation_lifecycle(db_path, *, relation_id) -> str`
    (sets `lifecycle_status`/`quarantine_reason`); `db.detect_bridge_risk_relations
    (db_path) -> list[str]`.
  - P5/P7 — `db.connected_components(db_path, *, only_active=True) ->
    list[set[str]]`; `db.graph_audit(db_path) -> list[dict]` (each violation has
    `code` + offending `subject_id`; empty list == clean).
- **Remaining P2 work (later modules / phases):** frozen hierarchy benchmark
  thresholds + multi-metric comparison fixtures (needs P5 labels), idempotent
  rebuild no-amplification (§27.8, `db.rebuild_graph_generation`), full
  `reconcile_source_change` downstream-closure assertions (§27.8), graph-audit
  wiring into `wiki lint` (§27.6), and the `gaussian_splatting` testbed run
  (§27.10).

## ⚠️ Pre-existing red baseline (NOT introduced by this work)
- `test_spec_sync.py` has 4 failures: P1 bumped the four spec titles to v0.9.0
  while backend `__version__`/`pyproject` and the test's `ACTIVE_VERSION` are
  still `0.8.0` (version bump is deferred to plan P10). The test couples spec
  titles ↔ backend version, so it is red across the P1→P9 docs-first window and
  goes green at P10's version bump. Confirm with the user whether to bump
  `ACTIVE_VERSION`/`__version__` now or leave it as the expected docs-first gate.

## Earlier Progress (P0/P1)
- **P1 schema gate APPROVED** (2026-06-14, Claude): user approved the locked
  `SCHEMA.md` §21 design (`SCHEMA_VERSION 8→9`, target v0.9.0) at the plan's
  mandatory schema gate. Committed `ded3886`.
- **P1 (docs-first contracts) COMPLETE** (2026-06-14, Claude). All P1
  deliverables written, committed, no code / no behavior change:
  - `SCHEMA.md` §21 + §11 version-history narrative (`ded3886`, `e3f33ef`).
  - `SYSTEM_BEHAVIOR.md` §27 (resolution/support/lifecycle/hierarchy/reports/
    graph-audit/migration/reconciliation/GQ07/testbed) + `SEARCH_ENGINE_SCHEMA`
    §11 (graph-quality materialization) + `PLUGIN_SCHEMA` title→v0.9.0, "no
    plugin contract change" note (`c419c66`).
  - EN→KR guides: `WORKFLOW_GUIDE(_KR)` §11, `USER_GUIDE(_KR)` Graph Quality
    section (`cca6d63`).
  - Three core spec domains synced to v0.9.0 in their titles.
- **⛔ STOPPED AT MANDATORY GATE (before P2 application code).** Per plan
  "Mandatory Stop" / Stop Conditions: stop before any application code until P1
  contracts are approved. The schema design is approved and the full P1 contract
  set is now frozen. **Next phase = P2** (failing resolution/relation/hierarchy
  gold tests — adversarial fixtures, graph-audit tests, frozen hierarchy
  benchmark fixtures). P2 is TDD test-writing (still pre-implementation per plan)
  but is the start of the code-bearing phases; awaiting user go-ahead to begin
  P2 before writing any tests/code.

### Update (2026-06-14, Claude) — P2 review rejection resolved (3 flaws fixed)
A review rejected the P2 gold tests for two mathematical contradictions and one
test-cynicism (oracle-leakage) failure. All three are now fixed; specs and tests
are internally consistent. Still pure TDD-red (no production code): full suite =
**824 passed, 8 xfailed, 37 failed** (33 intended Plan C reds + 4 pre-existing
`test_spec_sync` version-gate reds). Every Plan C red still fails via an
intention-revealing `assert <v9 api> is not None`, never `ImportError`. ruff clean.

1. **Corroboration threshold contradiction (`copied_source_only` vs `active`).**
   The frozen schema previously said `active` needs `≥1 verified independent
   support`, yet `copied_source_only` quarantines a relation whose only support
   is a single source lineage (independent count = exactly **1**). Under `≥1`
   those two states overlap — a 1-lineage edge would satisfy both. Resolved by
   **raising the corroboration threshold to ≥2 distinct `source_lineage_hash`**,
   making the partition total and disjoint: **0 → `unsupported`; exactly 1 →
   `copied_source_only` (single uncorroborated source); ≥2 → `active`**. Updated
   `SCHEMA.md` §21.5/§21.6/§21.8 and `SYSTEM_BEHAVIOR.md` §27.2/§27.3/§27.6/§27.8
   (incl. graph-audit invariant "0 active relations with fewer than 2 independent
   source lineages" and the reconciliation drop-out rule). Tests now pin the
   boundary explicitly: `test_copied_source_only...` asserts `distinct_lineages
   == 1`, `test_fully_supported_canonical_edge_is_active` asserts `== 2`. The
   stale "≥1" wording in `test_plan_c_hierarchy_audit.py`'s audit message was
   realigned to the ≥2 floor (its 0-support fixture is below either threshold, so
   behavior was already correct — only the phrasing was inconsistent).

2. **Tautological reversal illusion (`test_merge_reversal_restores_origin_and_
   provenance`).** The test did propose → accept → reverse → assert endpoints ==
   `before_pair`; a no-op `accept` would pass it trivially (endpoints never
   change, so the post-reverse check is vacuous). Fixed by adding an explicit
   **intermediate (post-accept, pre-reverse) assertion** that `accept` actually
   re-pointed the relation endpoint from the redirected origin onto the surviving
   canonical entity — `mid_pair == (survivor, other)` and `mid_pair !=
   before_pair` (§27.1 / SCHEMA §21.3 rewrite contract). Now reversal is only
   meaningful because accept provably mutated the graph first.

3. **Oracle leakage in bridge detection (`test_noisy_bridge_single_edge_is_
   flagged_bridge_risk`).** Previously the bridge edge alone had confidence 0.25
   while every intra-cluster edge was 0.9, so a trivial `confidence < 0.5` filter
   would pass without any topology. Fixed by densifying cluster A to a 4-node
   2-edge-connected block and adding a **second, equally low-confidence (0.25)
   edge INSIDE that dense cluster** (`a2→a4`, a redundant chord — not a cut
   edge). The test asserts only the true structural bridge (`a1→b1`) is flagged
   and the intra-cluster noisy chord is NOT. Bridge and chord now share the same
   low confidence, so confidence cannot discriminate — only genuine cut-edge
   topology passes.

### Update (2026-06-14, Gemini)
**Intercept P3: UI Context Bug Hotfixes (COMPLETED)**
Both UI context injection bugs have been successfully analyzed, fixed, tested, and merged into the active feature branch (`feature/plan-c-graph-quality`):
1. **PDF Crop context missing**: Dedup logic fixed to allow multiple distinct crops from the same page (`imageBase64` comparison). Secondary issue fixed: crop refs now use empty text content (`""`) instead of duplicating 3000+ chars of full-page text, correctly remaining a visual-only primary focus.
2. **Purple Pin eye-off reset**: Removed unconditional `activeContextExcludedKeys.clear()` on leaf change, allowing the user's manual exclusion state to persist across tab switches.

All 363 tests pass. **P3 implementation is now unblocked and ready to resume.**

### Update (2026-06-14, Gemini) — P3 Code Review & Approval
I have conducted a line-by-line audit of the P3 entity resolution and v9 migration foundation (`9f945d8`).
**Architectural Verdict: APPROVED.**
- **Reversible Merge Logic**: The `accept_entity_merge` implementation correctly captures and replays relation endpoints, accurately preserving origin identity via `redirected`. The logic gracefully handles self-loop rewrites via sequential updates.
- **Merge Guards**: `evaluate_merge_guards` rigorously implements §27.1, utilizing `frozenset` for order-independent avoid list matching and strict set intersections for context overlap.
- **Migration Additivity**: The v9 schema migration is strictly additive and idempotent.

**Next Action: P4 (Relation Support Aggregation + Quarantined Topology)**
The Executor must proceed with P4 to implement the relation lifecycle and topology hooks (`QUARANTINE_REASON_CODES`, `compile_relation_lifecycle`, `detect_bridge_risk_relations`), aiming to turn the remaining 6 `test_plan_c_relation_topology.py` gold tests green.

### Update (2026-06-14, Gemini) — P4 Code Review & Approval
I have audited the uncommitted P4 relation lifecycle and topology implementation.
**Architectural Verdict: APPROVED.**
- **Topology (Tarjan)**: `detect_bridge_risk_relations` implements iterative Tarjan cut-edge detection flawlessly, safely managing parallel edges via index tracking and strictly checking density (`v_side >= 2 and u_side >= 2`).
- **Support & Lifecycle**: `_classify_relation_lifecycle` strictly sequences admissibility checks (self-loop → endpoint_unresolved → contradiction → bridge_risk) before support corroboration, faithfully capturing §21.5/§21.6.
- **D2 Holdout Protection**: The manual SHA re-pin in `D2_HOLDOUT_RESULT.yml` correctly isolates the lexical search metric from graph backend edits.

**Next Action: P5 (Hierarchy Benchmark + Deterministic Implementation)**
The Executor must proceed with P5 to implement the fallback filtered connected components logic and benchmark-driven hierarchy gating.

### 🚨 INTERCEPT (2026-06-14, Gemini) — Critical Hotfix: PDF Crop Context & Line Extraction Regression
**HOTFIX EXCEPTION TRIGGERED:** The user reports that the previous UI context hotfix is completely non-functional and caused a regression:
1. `ctrl + shift + x` PDF crop context is still not being recognized in the Sidechat reply, or it gets completely buried/overwritten by the background context.
2. The originally working "line extraction" is now broken as well.

**Immediate Next Action (OVERRIDING P6):**
The Executor (Claude Code) MUST halt the pipeline immediately and resolve this critical bug first.
1. Commit the currently unstaged P5 work to the `feature/plan-c-graph-quality` branch so it is safely saved.
2. Create a new hotfix branch off the current branch (e.g., `hotfix/pdf-crop-regression-fix`).
3. Diagnose and fix the PDF crop context injection and line extraction regressions in the plugin. Ensure tests pass.
4. Merge the fixed hotfix branch back into `feature/plan-c-graph-quality`.
5. **Mandatory:** Push the branch to the remote repository.
6. Return to P5 only after this is complete.

# Cross-Agent Relay State

## Status: P3 COMPLETE — next action is P4 (relation support aggregation + quarantined topology)

**Branch:** `feature/plan-c-graph-quality`
**Target Plan:** `.agents/plans/C_graph_quality.md`

## Goal
Implement Batch 2: Plan C (Graph Quality) to stabilize the graph layer, establish community reports, and synthesize insights. The previous milestone (Plan B) has been successfully merged and shipped.

## Immediate Next Action
**P4 — relation support aggregation and quarantined topology.** P0–P3 are complete;
the v9 migration foundation and the entity-resolution lifecycle/reversal API are
implemented and the 19 P3 gold tests are green. P4 turns the remaining
`test_plan_c_relation_topology.py` reds (6) green by implementing the pinned P4
hooks the RELAY/specs already name:
- `db.QUARANTINE_REASON_CODES` (frozen 6-code set, SCHEMA §21.6) — this is the one
  remaining red in `test_plan_c_graph_quality.py`
  (`test_duplicate_proposition_is_not_a_quarantine_reason`).
- `db.compile_relation_lifecycle(db_path, *, relation_id) -> str` (sets
  `lifecycle_status`/`quarantine_reason` from §21.5/§21.6 support + structural rules:
  0 lineages → `unsupported`; exactly 1 → `copied_source_only`; ≥2 → `active`;
  self-loop/contradiction/endpoint_unresolved/bridge_risk routing).
- `db.detect_bridge_risk_relations(db_path) -> list[str]` (cut-edge topology, NOT a
  raw-confidence threshold per GQ07 §21.9).
The schema columns these need (`lifecycle_status`, `quarantine_reason`, `edge_class`,
`topology_weight`, `reeval_trigger`, `generation_id`) ALREADY EXIST — P3's migration
foundation added them; P4 is logic-only, no new migration. P5 (`connected_components`,
hierarchy) and P7 (`graph_audit`) own the 6 `test_plan_c_hierarchy_audit.py` reds.

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

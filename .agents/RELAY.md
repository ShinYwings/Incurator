# Cross-Agent Relay State

## Status: P2 COMPLETE — next action is P3 (entity resolution implementation)

**Branch:** `feature/plan-c-graph-quality`
**Target Plan:** `.agents/plans/C_graph_quality.md`

## Goal
Implement Batch 2: Plan C (Graph Quality) to stabilize the graph layer, establish community reports, and synthesize insights. The previous milestone (Plan B) has been successfully merged and shipped.

## Immediate Next Action
**P3 — entity resolution implementation.** P0, P1, and P2 are all complete; the
33 TDD-red gold tests are written and verified. The next phase turns the P3
resolution subset green by implementing the pinned v9 API hooks
(`db.RESOLUTION_STATUS_CODES`, `db.MERGE_DECISION_CODES`,
`db.evaluate_merge_guards`, `db.propose_entity_merge`, `db.accept_entity_merge`,
`db.reverse_entity_merge`) plus the v9 migration foundation those tests pin.
(The historical "Next phase = P2" note in the Earlier Progress section below is
from the P1 stop gate and is now superseded.)

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

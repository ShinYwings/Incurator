# Cross-Agent Relay State

## Status: IN PROGRESS (P2 — failing gold tests, TDD pre-implementation)

**Branch:** `feature/plan-c-graph-quality`
**Target Plan:** `.agents/plans/C_graph_quality.md`

## Goal
Implement Batch 2: Plan C (Graph Quality) to stabilize the graph layer, establish community reports, and synthesize insights. The previous milestone (Plan B) has been successfully merged and shipped.

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

## P2 STARTED (2026-06-14, Claude) — failing gold tests
- New module `backend/tests/test_plan_c_graph_quality.py`: 9 TDD-red gold tests
  covering the v9 migration foundation + both corrected flaws (schema-version,
  new-table/column creation, infer-nothing backfill, homonym surrogate key,
  exact-dup rejection, support aggregation/independence-by-lineage, and the
  `duplicate_proposition`-absent contract). All 9 fail for intended reasons
  (v9 schema/constants not built yet) with intention-revealing messages; ruff
  clean. Full suite: 824 passed, 9 new intended reds, 8 xfailed.
- **P4 API hook the tests pin:** `db.QUARANTINE_REASON_CODES` (frozen 6-code
  set) must be defined when relation lifecycle lands.
- **Remaining P2 fixtures to add (follow-on modules):** synonyms, abbreviations,
  multilingual aliases, type conflicts, `avoid_merges`/contradiction guards,
  ambiguous-alias non-resolution, merge proposal→accept→reversal lineage,
  self-loops, noisy bridges, copied-vs-independent support, edit/delete
  reconciliation, graph-audit assertions, and the frozen hierarchy benchmark +
  connected-components baseline (plan P2 list).

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

# Cross-Agent Relay State

## Status: P8 COMPLETE (sequential role reviews — PASS, 0 blocking). Pushed `7ddd252`. Next: P9 full CI → P10 release.

### P8 — Sequential Role Reviews (2026-06-15, Claude) — VERDICT: PASS (0 blocking)
Ran the 7 review personas over the P7 cutover (`cd4216f` + `7ddd252`). All pass;
findings are non-blocking observations (no capture→plan→approve re-entry needed).
1. **coder_engineer** — scope matches plan §360–379 + the user's full-cutover
   decision. graph_audit, support writer, compile_global_l3 swap, lint surface all
   present; no scope creep. PASS.
2. **peer_reviewer** — coupling/runtime: `_write_relation_supports` O(spans×units),
   `graph_audit` O(V+E+supports+reports), `persist_graph_data` support write is
   ON-CONFLICT idempotent. OBSERVATION (non-blocking): a full `compile_source_l2`
   re-run can add a second support row for the same evidence under a new KNU id, but
   it shares the source lineage so the independent count stays 1 — NO false active
   (the ≥2 floor needs 2 distinct SOURCES). The status-precedence branch in
   `_write_relation_supports` is dead-but-defensive (a unit's status is constant).
3. **schema_guardian** — no new migration (logic-only on v9 columns). Support PK
   `(relation_id, knowledge_unit_id, support_hash)`; `support_hash =
   _sha16([... relation_id, sorted spans])` deterministic; per-source SPAN ids keep
   cross-source support_hashes distinct (no collision). Endpoint/lineage integrity
   correct after the dangling-endpoint fix. PASS.
4. **source_pair_analyst** — B claim-support consumption: supports attributed by
   span intersection to the asserting unit, `support_status` mirrors KNU eligibility;
   prose grounds strictly in `report.source_span_ids` (eligible verified active
   closure). No broad-span fallback. PASS.
5. **qa_runner** — backend 870 passed (4 docs-first reds only), ruff clean, mypy 0
   new (70 pre-existing), plugin vitest 370; testbed graph_audit clean post-update,
   correctly flagged the legacy report pre-update. PASS.
6. **docs_sync_manager** — EN→KR parity: USER_GUIDE(+_KR) + WORKFLOW_GUIDE(+_KR)
   both gained the matching ≥2-source bullet; SYSTEM_BEHAVIOR §27.6 line 1966 already
   covers "0 endpoints that are not canonical entities" (so the dangling-endpoint
   flag needs no spec change). PASS.
7. **legacy_sweeper** — F401/F811/F841 clean; old broad-span
   `detect_communities`/`generate_community_report` are off the serving path,
   referenced ONLY by `test_community_reports.py` + the frozen
   `test_failure_atlas_repro.py` (so intentionally retained, not orphaned). No stale
   qmd/EXH refs introduced. OBSERVATION: their full excision is deferrable to a later
   cleanup once the failure-atlas repro is re-pinned. PASS.

### Re-review fix (2026-06-15, Claude) — graph_audit dangling-endpoint false negative

### Re-review fix (2026-06-15, Claude) — graph_audit dangling-endpoint false negative
Reviewer caught a blind spot: `graph_audit` whitelisted `state is None` (an
endpoint id absent from `graph_entities` — a dangling reference), silently
ignoring a broken authoritative reference. A non-existent endpoint is NOT
canonical. **Fixed at root cause:** only an explicitly `"canonical"` state
continues; `None` now flags `endpoint_not_canonical` with a "dangling reference"
detail. New regression lock `test_graph_audit_flags_active_relation_with_dangling_endpoint`.
Suite **870 passed** (4 docs-first reds only); ruff clean; mypy 0 new. D2 db.py
re-pinned `5220ac73 → f5e4382c`.

**Branch:** `feature/plan-c-graph-quality`
**Target Plan:** `.agents/plans/C_graph_quality.md`

## Goal
Implement Batch 2: Plan C (Graph Quality) to stabilize the graph layer, establish community reports, and synthesize insights. The previous milestone (Plan B) has been successfully merged and shipped.

## Immediate Next Action
**Claude**: 
1. **Commit and push** the validated P6 work on the `feature/plan-c-graph-quality` branch (as requested by the user).
2. Proceed to **P7 — graph audit + live integration + testbed** (plan §360–379).
P0–P6 are now approved. Execute the pipeline swap and ensure the `wiki lint` graph quality surfaces are connected.

Pinned hooks still to land in **P7**:
- `db.graph_audit(db_path) -> list[dict]` — each violation has `code` + offending
  `subject_id`; empty list == clean (flags active-without-≥2-lineages,
  redirected-endpoint reference, quarantined-missing-reason,
  report-finding-without-active-support). The 4 `test_plan_c_hierarchy_audit.py`
  reds are written and stay red until P7.
- **Live pipeline integration** (deliberately deferred to P7 per §27.8 staged
  publish — the prior graph generation keeps serving until the new graph audit
  passes): a `graph_relation_supports` **writer** (wire `graph_index.persist_graph_data`
  → support rows so relations can reach the ≥2-independent-lineage `active` floor),
  swap `compile_global_l3` / `detect_communities` from the broad-span CC path onto
  `db.rebuild_graph_generation`, and the `wiki lint` Graph Quality section (§27.6).
  Until then the OLD broad-span `community_reports.generate_community_report` path
  remains the serving path (untouched, surgical-change rule). The NEW P6 compiler
  is the staged claim-grounded path and is proven fallback-free by its gold tests.

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

**Immediate Next Action (OVERRIDING P6):**
The Executor (Claude Code) MUST halt the pipeline immediately and resolve this critical bug first.
1. Commit the currently unstaged P5 work to the `feature/plan-c-graph-quality` branch so it is safely saved.
2. Create a new hotfix branch off the current branch (e.g., `hotfix/pdf-crop-regression-fix`).
3. Diagnose and fix the PDF crop context injection and line extraction regressions in the plugin. Ensure tests pass.
4. Merge the fixed hotfix branch back into `feature/plan-c-graph-quality`.
5. **Mandatory:** Push the branch to the remote repository.
6. Return to P5 only after this is complete.

### ✅ INTERCEPT RESOLVED (2026-06-15, Claude) — PDF crop regression fixed (v0.8.1)
All 6 intercept steps complete. The crop/line-extraction regression is fixed at the
ROOT CAUSE and shipped on the feature branch.

- **Root cause:** the prior crop hotfix (`2b29aeb`) hard-coded the crop ref
  `content: ""` + image-only. That caused BOTH symptoms: (1) no
  `<primary_focus_selection>` anchor → the crop image was buried under the
  full-page background context; (2) all crop text ("line") extraction was lost.
  The original code pulled the WHOLE page text (the pollution bug that started
  this), so neither extreme was correct.
- **Fix (user-approved design: region-scoped text + image):**
  - `extractRegionTextFromSpans()` (pure, unit-tested, `pdfCapture.ts`) selects
    text-layer spans whose boxes intersect the crop rect (horizontal overlap +
    vertical-midpoint lasso), reading-order output, zoom-independent row grouping.
  - `externalPdfView.startSnippingMode` extracts the region text in mouseup and
    passes it via `onSnip(base64, pageNum, regionText)`; `main.ts` uses it as the
    crop `content` → wrapped in `<primary_focus_selection>`. Never whole-page,
    never empty; scanned regions fall back to image-only.
  - `chatSidebar.ts`: an image-only PRIMARY ref (scanned crop / dragged image) now
    emits an explicit primary-focus anchor instead of the weak "(Image context
    attached below.)" line — so image-only crops are also never buried.
- **Steps:** P5 was already committed (`6db0553`); branched
  `hotfix/pdf-crop-regression-fix`; implemented + TDD; merged `--no-ff` →
  `ffd7c92`; **pushed `origin/feature/plan-c-graph-quality`**; hotfix branch
  deleted (fully merged).
- **Validation:** plugin vitest **370 passed** (5 new pure-function cases + 2
  source-contract regression locks); `tsc --noEmit` clean; backend `ruff` clean;
  `test_spec_sync` unchanged at its **4 expected docs-first reds** (version bumped
  `0.8.0 → 0.8.1` across pyproject/package/manifest — stays on the 0.8 minor line;
  `test_backend_version_matches_active_spec_line` still green; P10 owns the 0.9.0
  cutover). Backend source byte-identical to P5 (only pyproject version touched).
- **Docs:** `PLUGIN_GUIDE(_KR)` §5 + `PLUGIN_SCHEMA` snip/primary-focus contracts;
  `CHANGELOG` `[0.8.1]`.
- **Next:** resume Plan C — Gemini reviews the committed P5
  `connected_components`, then **P6** (claim-grounded reports + reconciliation).
  P7 still owns the 4 `graph_audit` reds.
- **Note:** two unrelated working-tree edits (`GEMINI.md`,
  `.agents/workflows/Antigravity Strict Workflow.md` — Gemini's concurrency-guard
  rule) were left uncommitted/untouched (surgical-change rule); they are not part
  of this hotfix.

### Update (2026-06-15, Gemini) — P5 Code Review & Approval
I have conducted a line-by-line audit of the P5 deterministic hierarchy fallback (`6db0553`).
**Architectural Verdict: APPROVED.**
- **Determinism:** The `connected_components` union-find algorithm properly enforces a deterministic forest shape by rooting at `min(ra, rb)` and sorting the output components by `(size, sorted members)`.
- **Integrity Guard:** The python-side `if u in canonical and v in canonical:` successfully shields the active topology from redirected or phantom endpoints.
- **Holdout Protection:** `D2_HOLDOUT_RESULT.yml` narrative update correctly justifies the additive graph-compiler logic and successfully re-pins the tripwire.

**Next Action: P6 (Claim-Grounded Reports & Reconciliation)**
The Executor must proceed with P6 to implement the claim-grounded reports generation (`db.rebuild_graph_generation`, `reconcile_source_change`) and the reconciliation hooks, aiming to establish the gold fixtures and finalize the core synthesis path.

## P7 COMPLETE (2026-06-15, Claude) — graph audit + live claim-grounded cutover + testbed
**User chose the FULL AUTHORITATIVE CUTOVER** (vs §27.8 staged-publish). All P7
deliverables landed. Full suite: **869 passed, 8 xfailed, 4 failed** (was 859 at
P6; the only reds are the expected `test_spec_sync` docs-first version gate →
P10). `ruff` clean; `mypy` **0** new errors (70 pre-existing); plugin vitest
**370 passed** (P7 is backend-only). **Uncommitted** worktree (P6 `f3db15d` IS
committed; this worktree is P7 only + the two pre-existing unrelated Gemini files).

The "stuck" symptom was the D2 holdout tripwire firing (db.py SHA changed but
`D2_HOLDOUT_RESULT.yml` not re-pinned). Re-pinned twice as db.py grew:
`8c4d6e3a → 4a89f193` (graph_audit) → `5220ac73` (support writer), with a P7
narrative covering both ("across six phases").

**1. `db.graph_audit(db_path, *, conn=None) -> list[dict]` + frozen
`GRAPH_AUDIT_CODES`** (SYSTEM_BEHAVIOR §27.6 / SCHEMA §21.8): READ-ONLY assertion
pass (never writes). 4 schema-level §21.8 invariants —
active-relation-insufficient-support (<2 verified lineages),
reference-to-redirected / endpoint-not-canonical, quarantined-missing-reason,
report-finding-without-active-support. Sorted `(code, subject_id)`; `[] == clean`.
GQ07-dependent invariants (homonym false merge, mixed generations) stay
benchmark-later (no speculative checks, §21.9). All 4 `graph_audit` reds GREEN
(`test_plan_c_hierarchy_audit.py` fully green 6/6).

**2. `db.upsert_graph_relation_support(...)` + `persist_graph_data` wiring**
(§27.2): the graph_relation_supports WRITER. Aggregates ONE independent
claim-level support per asserting knowledge unit, keyed by the SOURCE'S LINEAGE
(`sources.content_hash`). `persist_graph_data` now takes `units` +
`source_lineage_hash` (threaded from `compile_source_l2` via the staged units +
`source["content_hash"]`); `_write_relation_supports` maps a relation to its
asserting unit(s) by SPAN INTERSECTION (never a broad-span fallback, F9). PK
`(relation_id, knowledge_unit_id, support_hash)` + `ON CONFLICT` ⇒ idempotent
recompile; one source = one lineage ⇒ a relation reaches `active` only when a
SECOND independent source corroborates the same proposition.

**3. Live `compile_global_l3` swap** (§27.5/§27.8): now calls
`db.rebuild_graph_generation` (deterministic claim-grounded skeleton + lifecycle
compile + stale-community retire) then `community_reports.generate_report_prose`
(NEW — fills prose by `community_key` via the merge-upsert, preserving the
skeleton's identity/grounding/dependency columns). The OLD broad-span
`detect_communities`/`generate_community_report` are NO LONGER on the serving
path (kept only as non-serving utilities — still referenced by
`test_failure_atlas_repro.py`, so not deleted; P8 legacy_sweeper can decide).
`rebuild_graph_generation` records the precise report→relation/report→span
dependencies, so the prose pass adds no broad dependency rows.

**4. `wiki lint` Graph Quality section** (§27.6): `lint.graph_quality(paths)` maps
each `db.graph_audit` violation to a release-blocking ERROR `LintIssue`
(`CheckId.GRAPH_QUALITY`), wired into `run_lint`'s fast checks; `cli.py` prints a
"Graph Quality: N findings (M release-blocking)" summary line beside Compiler
Integrity. Exits non-zero on a violation.

- **TDD — `tests/test_plan_c_live_integration.py` (3, all green):** support writer
  writes a verified lineage-keyed row + a single source quarantines
  `copied_source_only`; two INDEPENDENT sources corroborate ONE relation to
  `active` and `compile_global_l3` grounds a report citing that exact relation; a
  hand-forced active-without-support relation surfaces via `lint.graph_quality`.
- **`test_compile_global_l3_writes_concepts` rewritten** for 2 independent sources
  (distinct content_hash) — single-source can no longer ground a report (§27.2).

- **Testbed (gaussian_splatting, real LLM = AntigravityCli gemini-3.5-flash):**
  `VAULT_ROOT=<repo>/testbed wiki status|update|lint` all run. BEFORE update the
  Graph Quality audit correctly FLAGGED the legacy broad-span report
  `REP-5b7bde01` citing the known unsupported `REL-b6d5b9fc`; AFTER the new
  claim-grounded `wiki update` the audit is **CLEAN (`graph_audit == []`)** — 42
  verified supports written, 17 canonical entities, 18 relations all
  `quarantined`/`copied_source_only` (0 reached ≥2 independent lineages because the
  note/PDF sources don't extract byte-identical propositions), legacy report
  retired (served 1→0). The 20 remaining lint errors are ALL pre-existing Plan B
  `compiler_integrity` (F6 wrong-real-span) scenario data-quality issues, ZERO
  `graph_quality`. NOTE: a stray `backend/testbed` was accidentally created by
  `uv run --directory backend wiki` (VAULT_ROOT resolves relative to backend/) and
  REMOVED (Environment Integrity); always run the CLI from repo root with an
  absolute `VAULT_ROOT` to hit `<repo>/testbed`.

- **Docs:** `USER_GUIDE`(+`_KR`) Graph Quality + `WORKFLOW_GUIDE`(+`_KR`) §11 gained
  an explicit "community reports need ≥2 independent sources" bullet (the
  user-facing cutover consequence). SYSTEM_BEHAVIOR §27.6 / SCHEMA §21.8 already
  described the audit surface (authored at P1) and match the implementation.
- **D2:** re-pinned db.py `8c4d6e3a → 4a89f193 → 5220ac73`; additive
  graph-compiler/community-report/support-writer logic, NO retrieval/ranking/
  fusion/projection/embedding/chunking/materialize_chunks path → frozen Q06
  unaffected.
- **Next:** Gemini reviews P7, then **P8** (sequential role reviews) → P9 (full CI)
  → P10 (version bump 0.8.1 → 0.9.0, changelog, release).

## P6 IMPLEMENTED & VALIDATED (2026-06-15, Claude) — claim-grounded reports + precise reconciliation
**APPROVED by Gemini.**

Implemented the P6 deterministic claim-grounded graph-generation compiler and the
source-change reconciliation closure. **All 6 new in-scope P6 gold tests green**
(`test_plan_c_reports_reconciliation.py`). Full suite: **859 passed, 8 failed, 8
xfailed** (was 853 passed at P5; +6 = exactly the 6 new P6 gold tests, **zero
regressions**). `ruff check src/` clean; `mypy src/` adds **0** new errors (HEAD and
worktree both report the identical 70 pre-existing errors; the single db.py
`lastrowid` error just shifted 1353→1354 from the new `import hashlib`). **Not
committed** — per the P3/P5 cadence, stopped after turning green + updating this
relay so Gemini can review; the implementer/user owns the commit. P4 (`29b3ded`)
and P5 (`6db0553`) ARE committed; the uncommitted worktree is P6 only (plus the two
pre-existing unrelated Gemini files).

The 8 remaining reds are ALL out of P6 scope: 4 `test_plan_c_hierarchy_audit.py`
`graph_audit` tests (**P7**) + the 4 `test_spec_sync` docs-first version gate
(resolves at P10). **No new migration** — P6 is logic-only on the columns P3 already
added (`community_reports.member_hash/support_hash/config_hash/parent_community_key/
retired_at`).

- **TDD gold fixtures — `tests/test_plan_c_reports_reconciliation.py` (6):**
  claim-grounded report cites ONLY active relations (quarantined edge's far
  endpoint + spans excluded; no broad-span fallback); content/config-derived
  `community_key = f(level, member_hash, support_hash, config_hash)` (§21.7 — a
  changed active membership/support yields a NEW key, old community RETIRED);
  a component with no eligible active support emits no report; idempotent rebuild
  reuses the same `REP-` ids/keys with no count amplification (§27.8); a changed
  active-support closure changes `dependency_hash` (§27.5 fresh deps); and a
  one-source delete reconciles ONLY its closure (its supports → stale, its relation
  drops out of `active`, its community retires) while an unrelated community's report
  id/key is byte-identical.

- **db.py — `rebuild_graph_generation(db_path, *, config_hash=None, conn=None) ->
  dict`** (SYSTEM_BEHAVIOR §27.5/§27.8): the deterministic claim-grounded compiler,
  all inside one atomic transaction. (1) compiles every non-retired relation's
  lifecycle (P4) with ONE shared `detect_bridge_risk_relations` pass; (2) partitions
  active topology via `connected_components(only_active=True)` (P5), keeping only
  multi-node components; (3) derives content/config identity per community
  (`member_hash` over sorted canonical members, `support_hash` over the eligible
  verified active-support set, `community_key`, `dependency_hash` over the
  active-canonical-support **content** closure incl. entity content for §27.5
  freshness); (4) merge-upserts one `community_reports` skeleton per `community_key`
  citing the EXACT active relations + eligible-support span closure (NO whole-span
  fallback); (5) sets `retired_at` on every prior non-retired report whose key is
  absent from the rebuilt set (retire-before-synthesis); (6) records precise
  `artifact_dependencies` (report→relation, report→span). Idempotent by construction
  (content-derived keys → same ids reused → 0 amplification). Returns
  `{communities, reports, retired, community_keys}`.
- **db.py — `reconcile_source_change(db_path, *, source_id, removed_span_ids=None,
  config_hash=None, conn=None) -> dict`** (§27.8): marks verified relation supports
  whose span basis intersects `removed_span_ids` as `stale`, then re-runs
  `rebuild_graph_generation` so relations dropping below the §21.5 ≥2-lineage floor
  leave `active`, affected communities retire, and untouched communities keep their
  key + `REP-` id (no collateral churn). Returns the measured closure
  (`stale_supports`, `source_id`, + rebuild summary).
- **P6 review fixes — round 1 (2026-06-15, Claude — applied + TDD-covered):** a
  reviewer flagged two defects in the just-written P6 code; both fixed with new gold
  assertions that go red against the pre-fix code. (1) **O(N) support scan** in
  `reconcile_source_change` — replaced the full-table load with a SQLite
  `source_span_ids LIKE` OR pre-filter (pushes scope into SQL) while KEEPING the
  Python exact set-intersection as a correctness guard (LIKE wildcards only broaden
  the match, so no false negatives; the exact check kills any over-match). New
  `test_reconcile_span_prefix_does_not_over_stale` locks that removing `SPAN-1` never
  stales `SPAN-10`. (2) **Write amplification** — `rebuild_graph_generation` now
  SKIPS the report upsert + dependency rewrite for any community whose non-retired
  row already carries the identical `dependency_hash` (a true no-op), so an unchanged
  rebuild / unrelated-source reconcile never churns `updated_at` or the dep rows. The
  two no-amplification tests now use a sentinel `updated_at` (live-timestamp compares
  were unreliable: same-second rebuilds share `_now_iso()` even when the row IS
  rewritten). db.py re-pinned `f126c5af` → `87517ee3` in D2.
- **P6 review fixes — round 2 (2026-06-15, Claude — applied + TDD-covered):** the
  reviewer caught two more. (3) **Unsafe LIKE needle** — `json.dumps` stores a span
  id's `"` as `\"`, so the raw `%"sid"%` needle silently MISSED quote/backslash-bearing
  spans (a false-negative the Python guard can't recover → under-staling). Needle is
  now `f"%{json.dumps(sid)}%"` (exact JSON literal, matching how the array is stored).
  New `test_reconcile_matches_span_id_with_double_quote` locks it. (4) **SQL var-limit
  crash** — unbounded `IN (?, …)` / `OR` clauses would exceed SQLITE_MAX_VARIABLE_NUMBER
  on a large community/source. `reconcile_source_change` now CHUNKS the LIKE clause via
  the existing `_chunked` (size 900), and `rebuild_graph_generation` was rewritten to
  use a FIXED set of bulk fetches (all active relations / verified supports / canonical
  entities once) grouped in Python by a `comp_of` member→community map — eliminating
  ALL per-community `IN` clauses, byte-identical hashes preserved (same sort order).
  New `test_reconcile_handles_more_removed_spans_than_var_limit` (1501 removed spans)
  proves the chunk boundary. db.py re-pinned `87517ee3` → `8c4d6e3a` in D2. P6 gold
  tests now **9** (6 original + prefix + quote + chunk).
- **db.py — `graph_config_hash()` / `_GRAPH_FALLBACK_CONFIG` / `_sha16`**: the
  degraded filtered-connected-components config identity (§27.4), content-hashed so a
  fixed (graph, config) reproduces the same `community_key`. No Leiden (still BLOCKED
  on GQ07 labels).
- **db.py — extensions (additive, all existing callers green):**
  `upsert_community_report` is now a MERGE-upsert (every column defaults to None =
  *preserve existing*, so the rebuild skeleton's structure/identity and the LLM
  prose pass can write the SAME `community_key` row without clobbering each other;
  `clear_retired` un-retires a re-emitted community) + accepts `member_hash/
  support_hash/config_hash/parent_community_key` + `conn`. `list_community_reports`
  now excludes retired by default (`include_retired=False` — a retired/stale report
  never serves/feeds synthesis, §27.5). `record_artifact_dependency` accepts `conn`
  for the atomic publish. Added `import hashlib`.
- **`docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml`:** re-armed the db.py drift
  tripwire — extended the `plan_c_rearm` narrative to cover P6 ("across four phases")
  and re-pinned `file_sha256` db.py `7a8555e6…` → `f126c5af…`. P6 is additive
  graph-compiler + community-report logic touching NO retrieval/ranking/fusion/
  projection/embedding/chunking/materialize_chunks path the lexical Q06 holdout
  exercises, so the frozen Q06 metric is provably unaffected.
- **Docs:** no behavioral spec/guide drift — P6 implements exactly the frozen P1
  contracts (SCHEMA §21.7, SYSTEM_BEHAVIOR §27.5/§27.8 authored at P1). The new
  functions are internal DB helpers (no new CLI/MCP/plugin surface), so guides stay
  in sync; the `wiki lint` graph-audit surface (§27.6) + live pipeline integration
  remain P7.
- **Scope boundary (P6 vs P7):** the LIVE LLM pipeline swap (`compile_global_l3` →
  `rebuild_graph_generation`) needs a `graph_relation_supports` writer that does not
  exist yet (relations currently have zero support rows, so the ≥2-lineage `active`
  floor would yield zero reports and break `test_compile_global_l3_writes_concepts`).
  Per §27.8 staged-publish (the prior generation keeps serving until the new graph
  audit passes), that writer + the pipeline swap + the `wiki lint` Graph Quality
  surface + the `gaussian_splatting` testbed are P7 work — the same pattern as P5,
  which shipped `connected_components` as an internal helper and deferred its lint
  surface to P7. The OLD broad-span path is therefore intentionally left untouched
  (surgical-change rule).

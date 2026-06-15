# Plan C Evidence Ledger (Coding-Time)

Program 2C — Entity/Relation Resolution And Hierarchical Community Quality.
Created at the start of P0 (immediately before any code), per
`.agents/plans/C_graph_quality.md` "Evidence Ledger Refresh Deliverable". The
Arena ledger (`graph_quality_arena/04_evidence_ledger.md`) was a planning
snapshot at a different SHA; this is the authoritative coding-time anchor.

Status: P0 in progress. No application code authorized until P0/P1 contracts and
the hierarchy benchmark are written and the user approves (plan "Mandatory Stop").

## Current Repository And Schema Reality

- Rollback anchor SHA: `bcfb36a3dc394cfdd2b269b397fb0f217f80d970`
  (= `master` tip, the Plan B merge commit, PR #29). Branch
  `feature/plan-c-graph-quality` has **no commits of its own yet**
  (`git merge-base HEAD master == HEAD`); it sits exactly at merged B.
- `SCHEMA_VERSION = 8` (`backend/src/curator/db.py:23`), the Plan B schema. Plan
  C's additive migration will bump this to **9**.
- Product version: `0.8.0` in `backend/pyproject.toml`, `plugin/package.json`,
  and `plugin/manifest.json` (all three agree). Plan C will bump to one agreed
  version at P10.
- Toolchain: Python `3.11.11`, stdlib `sqlite3` against SQLite `3.45.3`.
- Community detection uses a **hand-rolled `_UnionFind`**
  (`pipeline/community_reports.py:34`); there is **no `networkx`** dependency.
  Any Leiden/weighted-partition candidate in P5 introduces a new dependency that
  must be pinned and recorded here before adoption.

### Graph Schema At This SHA (source of truth = `db.py`)

- `graph_entities` (`db.py:290`): deduplicated by a UNIQUE index on
  `(canonical_name, entity_type)` (`idx_graph_entities_name`, `db.py:301`).
  Columns: `id, canonical_name, entity_type, description, source_span_ids,
  knowledge_unit_ids, prompt_run_id, created_at, updated_at`. **No** alias,
  proposal, decision, redirect, or reversal-lineage column exists.
- `graph_relations` (`db.py:305`): `(source_entity_id, target_entity_id,
  relation_type)` collision is resolved by **overwrite** in
  `upsert_graph_relation` (`db.py:2261-2283`) — `description`,
  `assertion_source`, `source_span_ids`, `confidence` are all replaced
  (latest-write-wins). There is **no** independent per-claim support record,
  lifecycle status (active/provisional/quarantined/retired), quarantine reason,
  topology-weight, or re-evaluation-trigger column.
- `community_reports` (`db.py:323`): has a `level` column (default 0) and a
  `dependency_hash`, but detection only ever produces level-0 components.
- `compiler_generations` / `claim_supports` / `knowledge_units` carry the Plan B
  claim-support lifecycle (`support_status ∈ {unchecked, verified, failed,
  stale}`) that Plan C must consume but not re-derive.

### Behavioral Reality (confirmed by reading the code, not assumed)

1. **Entity resolution is exact-string only.** `upsert_graph_entity`
   (`db.py:2175`) merges on exact `(canonical_name, entity_type)`, unioning
   spans/units and filling an empty description. Synonyms, abbreviations,
   multilingual aliases, and homonyms are **not** handled; nothing prevents two
   different real-world entities that share a canonical string from being fused,
   and nothing links two surface forms of one entity.
2. **Relation support is destructively overwritten.** A second extraction of the
   same `(src, tgt, type)` triple discards the first extraction's spans and
   confidence. Independent claim-level support cannot accumulate; source lineage
   is not tracked, so copied sources would (once support exists) be
   indistinguishable from independent corroboration.
3. **Graph extraction is batch-local** (`graph_index.py:82-115`): entities are
   resolved to ids only within `persist_graph_data`'s `name_to_id` map for one
   call; cross-batch / cross-source identity relies entirely on the exact-name
   unique index.
4. **Community detection = connected components over ALL relations**
   (`detect_communities`, `community_reports.py:58`). No filtering by support,
   confidence, edge class, or assertion source. `CommunityPlan` has **no
   `level`** field; every report is written at level 0. Authored vs extracted
   topology is **not** distinguished at partition time.
5. **Community reports can fall back to the broad community span set.**
   `generate_community_report` passes
   `source_span_ids = getattr(parsed, "source_span_ids", []) or span_ids`
   (`community_reports.py:211`), where `span_ids` is the union of **every** span
   on **every** entity/relation in the component. When the model omits precise
   support, the report silently claims grounding in the entire community span
   set — the exact broad-span fallback Plan B handed off to Plan C.
6. **Existing tests** cover connected-components grouping and report
   dependency-hash changes; they do **not** cover resolution safety, support
   aggregation, hierarchy quality, edge-class separation, quarantine, reversal,
   or edit/delete reconciliation.

## Baseline And Rollback Evidence

- Active testbed scenario: **`gaussian_splatting`** — workspace
  `testbed/01_Workspaces/Gaussian Splatting Geometry Lab`. (Confirmed by
  inspecting the live testbed, per the CLAUDE.md scenario-discovery rule; not a
  default to `testbed_template`.)
- Published claim-generation identity at baseline:
  - `GEN-bc1dc52a` — source 2, **authoritative**, `curator.knowledge_unit_extract@v2`
  - `GEN-57bd7593` — source 3, **authoritative**, `curator.knowledge_unit_extract@v2`
  - `GEN-3555ceef` — source 1, **discarded**
  - C must compile only these authoritative generations and must refuse mixed
    generations (plan Stop Condition).
- DB backup: `testbed/.curator/state.sqlite.C-baseline.bak` created with
  `sqlite3 .backup` (online-consistent). `PRAGMA integrity_check` → `ok`.
  Restore rehearsal: row counts match the live DB across `knowledge_units` (22),
  `claim_supports` (22), `graph_entities` (2), `graph_relations` (1),
  `community_reports` (1), `synthesis_nodes` (1), `compiler_generations` (3).
  The `.bak` is gitignored (under `testbed/`), an operational artifact only.

## P0 Measured Baseline (Graph Audit At This SHA)

Read-only metrics from the live testbed DB (no behavior change):

| Metric | Baseline value | Note |
|---|---|---|
| Entities | 2 | `conic view consistency` (concept), `4x4 homography matrix` (method) |
| Relations | 1 | `REL-b6d5b9fc`: `addresses`, `system_infers`, conf `0.70`, `source_span_ids=[]` |
| Community reports | 1 | `REP-5b7bde01` / `comm-8a7993399447`, level 0, 2 entities · 1 relation · 1 span |
| KU `support_status` | failed 12 · unchecked 8 · verified 2 | from `knowledge_units` |
| Relation confidence | min/max/avg = 0.70 (n=1) | single sample — see GQ07 note below |
| Giant-component ratio | 1.0 (2/2 nodes, 1 component) | trivial at this scale |
| Duplicate/alias entities | 0 detectable | scale too small to exercise |
| Homonym risks | 0 detectable | scale too small to exercise |

### Graph Concern Classification (P0 Deliverable)

Per P0 "Every graph concern is reproduced, disproven, accepted, or scheduled":

- **REPRODUCED (live, in the baseline DB):** *unsupported relation in
  authoritative topology.* The only relation, `REL-b6d5b9fc`, has empty
  `source_span_ids` and `assertion_source=system_infers`, yet it forms the sole
  community and drives `REP-5b7bde01`. This is a concrete instance of Plan C's
  "every active relation must have eligible claim-level support" gate failing
  today. → fixed by P4 (support aggregation + active/quarantine lifecycle).
- **REPRODUCED (by code reading, deterministic):** exact-name-only entity
  resolution (P3), destructive relation-support overwrite (P4), unfiltered
  connected-components partition with no edge classes / levels (P5), and the
  broad community-span report fallback (P6). Each is a definite property of the
  current code, not a probabilistic one.
- **SCHEDULED (cannot be reproduced at current testbed scale):** homonym false
  merges, abbreviation/multilingual aliasing, copied-source false independence,
  noisy bridges, self-loops, giant components, and hierarchy stability. The
  `gaussian_splatting` graph (2 entities / 1 relation) is far too small. These
  are **deferred to P2 adversarial gold fixtures** purpose-built to exercise
  each concern, plus a graph-scale fixture for confidence calibration.
- **SCHEDULED (P7 holdout, blocking — see below):** non-discriminative relation
  confidence (GQ07).
- **OUT OF SCOPE (confirmed absent, must stay absent):** vault quota, storage
  meter UI, admission control, auto-deletion. None present; none to be added.

### GQ07 — Discriminative Relation Confidence (Blocking, Scheduled For P2/P4)

Plan E P7 measured a guarded production copy where **all 1,180** relation
confidences fell in `0.9–1.0` (mean `0.966`): confidence carried no denoising
signal. The current testbed cannot reproduce this (n=1, conf `0.70`). Therefore:

- A **graph-scale relation-quality fixture with labels** must be built in P2
  before any confidence threshold becomes a serving-time contract.
- Every confidence-dependent mechanism (denoising, filtered expansion, weighted
  PPR, Leiden partitioning) stays `benchmark-later` until calibration evidence
  exists. P5 algorithm selection is **gated** on this, not the reverse: changing
  the partition algorithm cannot repair untrustworthy edge scores.

## Hierarchy Benchmark Freeze (P0 Deliverable)

P0 freezes the **benchmark contract** (metrics, thresholds, gating), not an
algorithm choice — algorithm comparison is explicitly `benchmark-later` and
blocked on GQ07. Locked here so P5 cannot move the goalposts:

**Frozen multi-metric gate (all must hold; modularity alone is insufficient):**

1. **Determinism** — identical input graph + config + seed ⇒ byte-identical
   hierarchy (community membership, levels, identities). Required, not scored.
2. **No unexplained giant component** — the largest community may not exceed an
   approved fraction of active nodes unless the partition records an explicit,
   audited reason. Threshold value frozen with the P2 graph-scale fixture (the
   current 1.0 ratio is a 2-node artifact and is not the threshold).
3. **0 homonym false merges** in the P2 adversarial resolution fixtures.
4. **Report-support grounding = 100%** — every report finding cites exact
   eligible claim-level support; **0** broad community-span fallback findings.
5. **Provenance completeness** — every community/report carries level, member,
   active-support, and config hashes sufficient to reconstruct and audit it.
6. **Correct-restructuring-over-stability** — a partition that splits/merges
   communities correctly must win even if it churns community ids; identities
   are content/config-derived, stale records are retired (not frozen for id
   stability).

**Candidate algorithms (compared only after GQ07 labels exist):** filtered
connected components (the explicit degraded fallback), confidence-denoised
connected components, authored-topology-aware components, and seeded weighted
Leiden. The fallback (filtered connected components) must remain selectable
without a silent mode change at all times.

## Current Dirty Worktree

- Pre-existing uncommitted doc edits to `.agents/RELAY.md` and
  `.agents/ROADMAP.md` (workflow state, unrelated to graph code).
- P0 added (this change): `.agents/plans/C_roadmap_evidence.md` (this file) and
  the gitignored `testbed/.curator/state.sqlite.C-baseline.bak`.
- No implementation branch divergence, no spec/guide/test/production-code change
  yet. Application code remains blocked until the P1 approval gate.

## Migration Rehearsal Status

- Forward-only additive migration (`SCHEMA_VERSION 8 → 9`) is **designed but not
  yet written** (P3). The plan's strategy: add resolution/support/status
  tables/fields; backfill exact canonical names as existing entities; mark legacy
  relations/support `unchecked/provisional` until rebuilt from the authoritative
  B generation; never infer accepted aliases or verified supports on migrate.
- Backup/restore rehearsal on the live testbed DB: **passed** (see above). The
  additive-migration + clean-rebuild rehearsal on a disposable DB copy is a P3
  deliverable and is **not yet executed**.

## Rollback Plan (Anchor)

- Before publish: discard the staged graph/report generation.
- Accepted-merge reversal: replay origin/rewrite lineage and regenerate affected
  relations/communities/reports/synthesis.
- Algorithm/dependency failure: fall back to explicitly labeled filtered
  connected components.
- Post-publish corruption: restore `state.sqlite.C-baseline.bak`, regenerate the
  disposable markdown/search projections, patch forward unless a documented
  rollback is required.
- After three repeated QA failures: activate `rollback_strategist`, restore the
  last stable state, return to planning.

## P7 Post-Validation (2026-06-15) — Live Claim-Grounded Cutover

**Scope decision:** user chose the FULL authoritative cutover (vs §27.8
staged-publish). The live L3 serving path is swapped onto the claim-grounded
compiler; single-source vaults no longer ground community reports (§27.2 ≥2
independent-lineage floor).

**Pre-validation (graph audit on the existing testbed DB):** `wiki lint`
surfaced one Graph Quality violation — legacy broad-span report `REP-5b7bde01`
cites the non-`active` relation `REL-b6d5b9fc` (the P0-recorded live unsupported
relation). The new read-only audit correctly flags the pre-cutover artifact.

**Post-validation (after the new-path `wiki update`, real LLM AntigravityCli
gemini-3.5-flash):**
- `graph_audit(testbed) == []` — CLEAN.
- 42 `graph_relation_supports` rows written (all `verified`) by the new
  `persist_graph_data` writer; 17 entities all `canonical`.
- 18 relations, all `quarantined`/`copied_source_only` — 0 reached ≥2 independent
  lineages (the note + PDF sources don't extract byte-identical propositions), so
  the conservative §27.2 behavior holds on real data.
- Legacy report retired (served community_reports 1 → 0); no spurious broad-span
  report regenerated.
- Remaining 20 `wiki lint` errors are ALL pre-existing Plan B
  `compiler_integrity` (F6 wrong-real-span) scenario data-quality issues — ZERO
  `graph_quality`.

**Test/CI evidence:** backend `869 passed, 8 xfailed, 4 failed` (the 4 reds are
ONLY the `test_spec_sync` docs-first version gate → P10); `ruff` clean; `mypy` 0
new errors (70 pre-existing); plugin vitest `370 passed`. New gold module
`tests/test_plan_c_live_integration.py` (3) + rewritten
`test_compile_global_l3_writes_concepts` (2 independent sources).

**D2 holdout:** db.py re-pinned `8c4d6e3a → 4a89f193 → 5220ac73` (graph_audit,
then support writer). Additive graph/report/support logic only; no
retrieval/ranking/fusion/projection/embedding/chunking/materialize_chunks path
touched, so the frozen lexical Q06 metric is provably unaffected.

**Env note:** a stray `backend/testbed` was created by `uv run --directory
backend wiki` (VAULT_ROOT resolves relative to backend/) and removed; the CLI
must run from repo root with an absolute `VAULT_ROOT=<repo>/testbed`.

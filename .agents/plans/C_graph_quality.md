# Program 2C Master Implementation Plan — Entity/Relation Resolution And Hierarchical Community Quality

Date: 2026-06-11
Status: DRAFT — dedicated Arena concluded; awaiting Program 1 and Plan B completion plus user approval before implementation
Arena: `.agents/plans/graph_quality_arena/`

## 0. Objective And Program Boundary

Program 2C is the second Evidence Compiler Integrity release. It compiles the
trusted claim generations published by B into a reversible, support-aware entity/
relation graph and a measured deterministic hierarchy whose reports remain
claim-level grounded and incrementally maintainable.

C is an independent Arena and release plan, but implementation has a hard
dependency on merged B. Graph heuristics cannot compensate for unchecked or
broadly grounded claims. Query-serving algorithms remain Program 3 work.

Vault quota, storage bars, admission limits, and automatic cleanup are explicitly
excluded and deferred to a separate storage-governance milestone.

## Strict Quality Condition

- 0 homonym false merges in approved adversarial fixtures.
- Every accepted alias/merge is auditable and reversible with complete origin
  and downstream rewrite lineage.
- Every active relation has eligible claim-level support; unsupported/noisy
  relations are provisional/quarantined with reason and cannot silently affect
  authoritative communities.
- Authored and extracted topology remain distinguishable.
- Hierarchy is deterministic under fixed graph/config/seed, provenance-complete,
  and has no unexplained giant component.
- Community reports cite exact claim-level support and have fresh dependency
  hashes; no broad community-span fallback is allowed.
- Unchanged rebuild causes no entity/relation/report count amplification; source
  edit/delete changes only the expected graph/report/synthesis closure.

## Locked Design Decisions (Arena Consensus)

1. C consumes only one fully published B claim generation and its approved
   support eligibility states.
2. Resolution lifecycle distinguishes alias, ambiguous alias candidate, merge
   proposal, accepted merge, rejected decision, and reversal.
3. Similarity is candidate generation only. Automatic similarity merge is
   rejected.
4. Exact/high-certainty aliasing still requires type/context/contradiction/
   `avoid_merges` guards.
5. Accepted merges preserve origin identities and complete downstream rewrite
   lineage so reversal can reconstruct the prior graph.
6. Relations are propositions with independent claim-level supports. Source
   lineage, not row count, determines support independence.
7. Relation lifecycle distinguishes active, provisional, quarantined, and
   retired. Only active relations enter authoritative community construction.
8. Quarantine records reason codes and re-evaluation triggers; it is not an
   opaque discard pile.
9. Authored links/topology and extracted semantic relations remain separate edge
   classes through weighting, hierarchy, audit, and reports.
10. Hierarchy selection is benchmark-driven and multi-metric. Seeded weighted
    Leiden is a candidate, not the goal; filtered connected components is the
    explicit degraded fallback.
11. Correct community restructuring wins over artificial ID stability.
    Community/report identities are content/config-derived and stale records are
    retired.
12. Community reports cite exact eligible claim support and cannot fall back to
    the whole community span set.
13. Quota is deferred. Artifact growth is measured only as duplicate
    amplification/compiler quality.

## Dependencies And Approval Gates

### Hard Prerequisites

- Program 1 is merged with frozen graph-quality evaluation, observability, and
  rollback contracts.
- Plan B is merged with:
  - published claim-generation identity;
  - verified/uncertain/unsupported support lifecycle;
  - stable claim/source lineage;
  - edit/delete/split reconciliation;
  - compiler audit and failure-injection gates.
- Plan B's compiler audit explicitly assigns every remaining graph/report
  broad-span fallback to Plan C; B is not required to remove Plan-C-owned
  community/report fallbacks before merge.
- Gold resolution and graph fixtures exist for synonyms, homonyms,
  abbreviations, multilingual aliases, copied-source support, contradictions,
  self-loops, noisy bridges, and edits/deletes.

### Ordering

```text
Program 1 merged
  -> B merged
  -> C specs and migration contract approved
  -> C implemented, validated, merged
  -> Program 3 begins
```

### Mandatory Stop

Stop before code after P0/P1 specifications and benchmark contract are written
and request user approval under the Universal Strict Workflow.

## Evidence Ledger

### Current Repository & Schema Reality

- Planning inspection SHA: `12cc63ec3c43cfdf2049215f314876842b079f2d`
  on `feature/editor-latex-copy`; implementation must refresh from merged B
  `master`.
- Entities deduplicate only exact `(canonical_name, entity_type)`.
- Entity upsert unions spans/knowledge units but lacks alias/proposal/redirect/
  reversal lifecycle.
- Relation upsert overwrites support fields for an existing endpoint/type triple
  rather than preserving independent support records.
- Graph extraction is batch-local.
- Community detection is connected components over all relations; current plans
  are level 0 despite the existing `level` column.
- Community reports hash entity/relation inputs but can fall back to broad
  community spans.
- Existing tests cover connected components and report hash changes, not
  resolution safety, support aggregation, hierarchy quality, or reconciliation.

### Current Dirty Worktree

- The planning worktree contains pre-existing shared/unrelated changes.
- This plan and Arena modify only user-assigned paths.
- No implementation branch, specs, guides, tests, ROADMAP, RELAY, umbrella plan,
  or production code was changed.

### Rollback Requirements

Immediately before coding:

1. Create a fresh branch from merged B `master`; update RELAY then.
2. Record exact SHA, published claim generation, schema/version, algorithm/
   dependency versions, seed/config, active scenario, and baseline graph metrics.
3. Back up `state.sqlite`; verify restore.
4. Rehearse additive migration and clean graph/report rebuild on disposable DBs.
5. Preserve old graph/report generation until the new graph audit passes.
6. Preserve merge/rewrite origin lineage sufficient for reversal.
7. Keep filtered connected components as an explicit degraded runtime fallback.
8. If migration/audit/hierarchy gates fail, restore the old graph generation or
   DB backup and return to planning after three repeated QA failures.

### Evidence Ledger Refresh Deliverable

Before implementation, create the required coding-time evidence ledger from the
approved Program 1/B template. The Arena ledger is a planning snapshot.

## Target Contract And Candidate Schema

Final names and normalization are frozen in specs before code. Candidate
additive records:

```sql
CREATE TABLE entity_aliases (
  alias_normalized TEXT NOT NULL,
  entity_id TEXT,
  alias_display TEXT NOT NULL,
  source_span_ids TEXT NOT NULL DEFAULT '[]',
  knowledge_unit_ids TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL DEFAULT 0.0,
  resolution_status TEXT NOT NULL,
  resolution_reason TEXT NOT NULL DEFAULT '',
  decision_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (alias_normalized, alias_display, resolution_status)
);

CREATE TABLE entity_merge_proposals (
  id TEXT PRIMARY KEY,
  source_entity_id TEXT NOT NULL,
  target_entity_id TEXT NOT NULL,
  decision TEXT NOT NULL,
  rationale TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE entity_resolution_lineage (
  decision_id TEXT NOT NULL,
  origin_entity_id TEXT NOT NULL,
  canonical_entity_id TEXT NOT NULL,
  rewrite_json TEXT NOT NULL,
  PRIMARY KEY (decision_id, origin_entity_id)
);

CREATE TABLE graph_relation_supports (
  relation_id TEXT NOT NULL,
  knowledge_unit_id TEXT NOT NULL,
  source_span_ids TEXT NOT NULL,
  assertion_source TEXT NOT NULL,
  confidence REAL NOT NULL,
  support_status TEXT NOT NULL,
  support_hash TEXT NOT NULL,
  source_lineage_hash TEXT NOT NULL,
  PRIMARY KEY (relation_id, knowledge_unit_id, support_hash)
);
```

Candidate relation fields: lifecycle status, quarantine reason, topology weight,
and re-evaluation trigger. Candidate community identity/config records are added
only after benchmark needs are specified.

## Migration And Rollback Plan

### Migration Strategy

1. Add resolution/support/status tables/fields forward-only.
2. Backfill current exact canonical names as existing entities, but do not infer
   accepted aliases or verified relation supports.
3. Mark legacy relations/support as unchecked/provisional until rebuilt from the
   published B claim generation.
4. Run read-only graph audit and baseline duplicate/unsupported/giant-component
   metrics.
5. Build a staged new graph generation with resolution decisions, support
   aggregation, active/quarantine policy, communities, and reports.
6. Compare entity/relation/report coverage, false merges, support provenance,
   hierarchy metrics, dependencies, and duplicate amplification.
7. Publish only after all gates pass; retain merge/rewrite lineage and prior
   graph generation until release confidence is established.

### Rollback

- Before publish: discard staged graph/report generation.
- Accepted merge reversal: replay origin/rewrite lineage and regenerate affected
  relations/communities/reports/synthesis.
- Algorithm/dependency failure: use explicitly labeled filtered connected
  components fallback.
- Post-publish corruption: restore DB backup and regenerate disposable
  projections/search; patch forward unless documented rollback is required.

## Execution Phases (Follow TDD And CI At Each Phase)

### P0 — Program Setup, Graph Baseline, And Benchmark Freeze

- Start fresh branch from merged B `master`.
- Refresh evidence ledger, active scenario, claim-generation identity, and graph
  audit baseline.
- Measure duplicate entities, candidate aliases, homonym risks, unsupported/
  overwritten relations, self-loops, noisy bridges, giant-component ratio,
  hierarchy stability, report support, and edit/delete reconciliation.
- Freeze the multi-metric hierarchy benchmark and approved thresholds.

Verify:

- No behavior change.
- Every graph concern is reproduced, disproven, accepted, or scheduled.
- Quota UI/limits are absent from scope.

### P1 — Docs-First Resolution, Relation, Hierarchy, And Migration Contracts

- Update all affected static specs synchronously:
  `SCHEMA.md`, `SYSTEM_BEHAVIOR.md`, `PLUGIN_SCHEMA.md` only if audit/review
  surfaces change, and `SEARCH_ENGINE_SCHEMA.md`.
- Update English guides first, then faithful `_KR.md` counterparts.
- Freeze resolution lifecycle, merge reversal, relation support/independence,
  edge classes/status, quarantine/recheck, hierarchy input/config/fallback,
  report support, reconciliation, migration, and rollback contracts.
- Stop for user approval before application code.

Verify:

- Specs, guides, benchmark, migration, and tests-to-be-written agree.
- No code behavior change.

### P2 — Failing Resolution/Relation/Hierarchy Gold Tests

- Add adversarial fixtures for exact duplicates, synonyms, homonyms,
  abbreviations, multilingual aliases, type conflicts, contradiction/
  `avoid_merges`, copied-source support, independent sources, self-loops, noisy
  bridges, ambiguous aliases, merge reversal, and edit/delete.
- Add failing graph-audit tests for endpoint/support/lineage/report freshness.
- Add frozen hierarchy benchmark fixtures and connected-components baseline.

Verify:

```bash
uv run --directory backend pytest -q <focused C tests>
uv run --directory backend ruff check src/
```

Expected: new behavior tests fail for intended reasons; unchanged legacy tests
remain green.

### P3 — Additive Schema, Resolution Lifecycle, And Reversal

- Implement additive migration and DB helpers for aliases, ambiguous candidates,
  proposals, decisions, accepted merges, rejections, reversals, and lineage.
- Implement deterministic normalization for candidate generation only.
- Enforce type/context/contradiction/`avoid_merges` guards.
- Preserve origin identity and unioned claim/span provenance.
- Update DB sync/export/import and inspection surfaces.

Verify:

- 0 homonym false merges in gold fixtures.
- Ambiguous aliases remain unresolved.
- Accepted merge reversal reconstructs original endpoints/provenance.
- Fresh/migrated/export-import/backup-restore tests pass.
- Focused pytest + ruff + mypy pass.

### P4 — Relation Support Aggregation And Quarantined Topology

- Version graph extraction prompt/validator contracts to consume eligible B
  claim support.
- Normalize endpoints through accepted resolution only.
- Persist independent relation supports using source lineage.
- Implement active/provisional/quarantined/retired lifecycle, reason codes, and
  re-evaluation triggers.
- Detect duplicate propositions, self-loops, unsupported edges, contradictions,
  and bridge-risk candidates.
- Keep authored and extracted edge classes distinct.

Verify:

- Latest-write support loss is eliminated.
- Copied sources do not count as independent support.
- Only active eligible edges enter community input.
- Quarantine is inspectable and re-evaluable.
- Focused pytest + ruff + mypy pass.

### P5 — Hierarchy Benchmark And Deterministic Implementation

- Benchmark filtered connected components against seeded weighted Leiden or
  approved alternatives on the frozen graph suite.
- Select a hierarchy only if multi-metric gates improve without homonym,
  provenance, report-support, or stability regression.
- Implement stable sorted input, explicit seed/config hash, hierarchy levels,
  and explicit degraded fallback.
- Define community identity from level/members/active-support/config hashes while
  allowing correct restructuring.

Verify:

- Fixed graph/config/seed yields identical hierarchy.
- No unexplained giant component.
- Filtered connected components fallback works without silent mode change.
- Focused pytest + ruff + mypy pass.

### P6 — Claim-Grounded Reports And Precise Reconciliation

- Generate reports from exact active relations and eligible claim supports.
- Remove broad community-span fallback.
- Record precise dependencies and retire stale communities/reports before
  synthesis consumes them.
- Reconcile alias/merge/relation/community/report/synthesis/search state after
  unchanged rebuild and source edit/delete.
- Inject failures at graph/report publish boundaries.

Verify:

- Every report finding has exact eligible claim support.
- Unchanged rebuild has no count amplification.
- Edit/delete changes only expected graph/report/synthesis closure.
- No orphan endpoints, stale aliases/supports/reports, or mixed claim generations.
- Focused pytest + ruff + mypy pass.

### P7 — Current Testbed And Graph Audit

- Initialize the confirmed active scenario and add current DB-native graph
  adversarial fixtures.
- Validate local Markdown/PDF and Reference Mode external sources.
- Run hierarchy/report generation with configured provider where available;
  otherwise run deterministic/local simulator gates and document blocker.
- Report graph metrics separately; do not implement quota.

Verify:

```bash
VAULT_ROOT=testbed wiki status
VAULT_ROOT=testbed wiki add
VAULT_ROOT=testbed wiki update
VAULT_ROOT=testbed wiki lint
```

Plus approved graph audit, resolution, relation-support, hierarchy, and report
scenario commands.

### P8 — Sequential Role Reviews

Run and record:

1. `coder_engineer`: scope and implementation against plan.
2. `peer_reviewer`: coupling, lifecycle, reversal, algorithm/runtime risks.
3. `schema_guardian`: schema, migrations, identity, endpoint, lineage integrity.
4. `source_pair_analyst`: B claim-support consumption and report grounding.
5. `qa_runner`: focused/full CI, migration, reversal, fallback, testbed.
6. `docs_sync_manager`: specs/guides English→Korean parity.
7. `legacy_sweeper`: exact-name/connected-component assumptions, stale qmd/EXH
   references, orphan APIs/tests/comments.

Any non-trivial review finding re-enters capture → plan → approval before code.

### P9 — Full Local CI And Release Gates

```bash
export UV_PROJECT_ENVIRONMENT="$(git rev-parse --show-toplevel)/.venv"
uv run --directory backend pytest -q
uv run --directory backend ruff check src/
uv run --directory backend mypy src/
npx vitest run -c ./plugin/vitest.config.ts
```

Also run migration/reversal rehearsal, graph audit, frozen hierarchy benchmark,
active testbed, and exact approved Program 1/B/C quality suite.

### P10 — Release Completion

- Clean resolved roadmap/report items only under the Universal Strict Workflow.
- Bump `backend/pyproject.toml`, `plugin/package.json`, and
  `plugin/manifest.json` to one agreed version.
- Update `CHANGELOG.md`.
- Delete implemented active plan files only at the workflow's required step.
- Final commit: `chore(release): vX.Y.Z`.
- Push branch and open detailed PR. Do not start Program 3 until C is merged.

## Quality Gates

### Resolution

- 0 homonym false merges in adversarial fixtures.
- 100% accepted aliases/merges have decision reason, evidence, source/claim
  lineage, and reversible rewrite lineage.
- 100% ambiguous aliases remain unresolved until an approved decision.
- `avoid_merges` and contradiction guards are enforced.

### Relations

- 100% active relations have eligible claim-level support.
- 0 copied-source rows incorrectly counted as independent support.
- 0 unresolved endpoints in authoritative topology.
- 100% provisional/quarantined edges have reason and re-evaluation trigger.
- Unsupported/noisy/self-loop/bridge-risk edges cannot silently enter
  authoritative communities.

### Hierarchy And Reports

- Fixed graph/config/seed produces identical hierarchy.
- No unexplained giant component under approved threshold.
- Approved multi-metric hierarchy gates pass; modularity alone is insufficient.
- 100% report findings cite exact eligible claim support.
- 0 broad community-span fallback findings.
- Filtered connected-components fallback is explicit and tested.

### Compiler Integrity

- Unchanged rebuild produces identical authoritative graph/report records,
  dependency hashes, and counts.
- One-source edit/delete changes only expected graph/report/synthesis closure.
- Graph audit finds 0 active orphan endpoints, stale aliases/supports/reports, or
  mixed claim generations.
- Migration, accepted-merge reversal, DB backup/restore, and fallback rehearsal
  pass.

### CI And Testbed

- Full local CI passes.
- Current graph testbed passes, or external provider/dependency blocker is
  explicitly documented while all lower-level gates pass.
- No quota UI, limits, admission control, or auto-deletion is implemented.

## Required Documentation Surfaces

- `docs/specs/curator_schema/SCHEMA.md`
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`
- `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`
- `docs/specs/plugin_schema/PLUGIN_SCHEMA.md` only if exposed audit/review
  contracts change
- Relevant English guides first, then matching `_KR.md` guides
- Prompt contract/evaluation documentation and current scenario plan

## Explicit Non-Goals

- Vault quota, storage meter UI, hard limits, admission control, or cleanup.
- Query routing, PPR, DRIFT, global serving, retrieval tuning, or context packing.
- Plan B source-pair/math/claim-support implementation.
- Similarity-only automatic entity merge.
- Treating authored links as equivalent to extracted factual relations.
- Automatic source/reference edits.

## Stop Conditions

- Stop now: planning only; no implementation is authorized.
- Stop before code until Program 1 and B are merged and P1 contracts are
  approved.
- Stop if C reads mixed/unchecked claim generations.
- Stop if accepted merges cannot be reversed with complete lineage.
- Stop hierarchy adoption if any homonym, provenance, report-support, stability,
  giant-component, fallback, migration, CI, or testbed gate fails.
- Stop immediately if quota enters implementation scope.
- After three repeated QA failures, activate `rollback_strategist`, restore the
  last stable state, and return to planning.

---

## Plan E P7 Research Handoff (2026-06-12)

Source: `backend/research_spikes/reports/p7.md`, `backend/research_spikes/manifests/p7.yml`.
Binding specification requirements handed off at Plan E P8; adoption still
flows through this plan's own phases, benchmarks, and gates.

### Blocking Requirement: Discriminative Relation Confidence

The guarded production copy showed every one of `1,180` relation confidences
in `0.9-1.0` (`mean=0.966`): current confidence carries no denoising signal.
Every confidence-dependent graph mechanism (denoising, filtered expansion,
weighted PPR, hierarchy partitioning) is gated on this plan delivering
relation-confidence values that actually separate weak edges from strong ones,
with labeled relation-quality data to prove it.

### Holdout Evidence: The Confidence Threshold Is A Correctness/Noise Dial (GQ07)

On the P7 holdout, a fixed `0.5` filter both blocked the noisy-bridge path
AND lost a true `0.25`-confidence ecology-link edge (filtered expansion recall
`0.50` vs unfiltered `1.00`); unfiltered traversal recovered the true edge but
re-surfaced the noise node at `165x` the traversal cost. REJECTED DEFAULT: a
fixed confidence threshold treated as a calibrated noise filter. This plan
must produce calibration evidence (per-relation-type quality labels or
equivalent) before any threshold becomes a serving-time contract.

### `benchmark-later` Inherited Comparisons

- Denoised hierarchy / Leiden: compare raw connected components,
  confidence-denoised components, authored topology, and fixed-seed Leiden
  ONLY after relation-quality labels exist; changing the partition algorithm
  cannot repair untrustworthy edge scores.
- Filtered/budgeted PPR: re-run only after graph identity, relation
  confidence, and authored-topology contracts pass this plan's gates.
- Update/delete behavior is part of any future benchmark: P7 re-verified
  deterministic seed stability and `0.0` churn for already-excluded edges;
  community-summary freshness and source-edit invalidation remain unmeasured
  and block mechanism adoption.

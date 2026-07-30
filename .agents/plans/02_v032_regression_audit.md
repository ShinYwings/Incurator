# v0.39.x Stability Regression Audit And Repair Master Implementation Plan

Date: 2026-07-30
Status: ACTIVE — P1–P3 complete; P4 delivery in progress
Umbrella: `.agents/plans/01_system_stability_overhaul.md`
Evidence: `.agents/plans/02_v032_regression_evidence.md`

## 1. Objective

Implement every confirmed finding from the second whole-system stability review
and perform a release-by-release regression audit from v0.32.0 through current
v0.39.0.

Definition of done:

- PR #101 has no unresolved authored-topology P0/P1 finding;
- every merged release from PR #80 through PR #100 plus current PR #101 has two
  consecutive audit passes with no new P0/P1 finding;
- all confirmed P0/P1 findings are fixed with docs and red-before-green tests;
- every confirmed P2 is fixed or explicitly retained in ROADMAP with exact
  evidence, owner, and reason;
- source deletion, compiler publication, sync/LWW, retrieval degradation,
  provider cancellation, MCP settlement, and durable state corruption are
  exercised through fault injection rather than happy paths only;
- full backend/plugin CI, current spec/version checks, isolated testbed smoke,
  and external Reference Mode boundaries pass;
- production `second_brain`, active testbed, and consumed D2 holdout remain
  untouched.

## 2. Explicit Non-Goals

- No v1.0/API freeze.
- No new feature, UI redesign, retrieval algorithm, graph schema, or sync
  transport format.
- No schema-v14 migration unless current schema is proven insufficient and a
  revised Minor plan receives separate approval.
- No one-shot rewrite of DB, LLMClient, MCP, or plugin persistence.
- No full replay of historical build environments when current-code
  contract/diff/fault analysis is sufficient.
- No mutation of production vaults, active testbeds, private Zotero libraries,
  or consumed holdout fixtures.
- No unrelated style cleanup, dead-code sweep, or performance optimization.

## 3. Strict Quality Conditions & Release Gates

- Every code fix begins with a failing regression test that reproduces the exact
  transition.
- Each phase passes its focused tests, `scripts/backend-check ruff`, and
  `scripts/backend-check mypy` before the next phase.
- Every plugin phase passes focused Vitest, full Vitest, TypeScript, and
  production build before release.
- Every changed behavior updates the relevant static spec and English guide
  first, then the matching Korean guide.
- Every repair revision is strictly greater than every observed valid LWW
  revision; equal-clock repairs are forbidden.
- Every shutdown/cancel/timeout settles pending work exactly once.
- Every corrupt existing durable file remains byte-preserved until an explicit
  recovery action; absence alone may initialize defaults.
- Search never reports unavailable vector/rerank work as full-quality success.
- Release audit closure requires two dry passes per release, with a finding/proof
  row for every behavior-bearing changed path.
- Full release gate per patch:
  - `scripts/backend-check pytest`
  - `scripts/backend-check ruff`
  - `scripts/backend-check mypy`
  - `npx vitest run -c ./plugin/vitest.config.ts`
  - `npx tsc --noEmit -p plugin/tsconfig.json`
  - `npm run build --prefix plugin`
  - `npm audit --prefix plugin`
  - `git diff --check`
  - version/spec/docs parity
  - isolated current-contract testbed and Reference Mode smoke.

## 4. Locked Design Decisions (Arena Consensus)

- **Delivery is a patch chain, not one mega-PR.**
  - PR #101/v0.39.0 receives only F02–F06 and F17–F18, because they are direct
    authored-topology review blockers.
  - Source lifecycle/compiler recovery, persistence, provider/MCP, and
    retrieval/prompt fixes ship from clean merged `master` as independent
    v0.39.x patch releases.
- **Audit method**: historical master plan + first-parent merge diff + current
  spec/test/code triangulation, followed by the shared fault-transition matrix.
- **Audit order**:
  1. identity/storage/sync releases;
  2. provider/plugin lifecycle releases;
  3. query/link/topology releases.
  Results remain recorded release-by-release.
- **No schema change for confirmed findings.** Existing `source_id`,
  generation audit, artifact dependencies, support tables, lifecycle state, and
  tombstones are sufficient until tests prove otherwise.
- **Source deletion** computes a dependency closure. Shared canonical artifacts
  are retired/tombstoned according to remaining support; device-local derived
  rows are hard-deleted.
- **Logical clocks** use one validated strict-successor helper for repair and
  retirement.
- **Compiler publication** keeps authoritative DB and derived projections
  recoverable through stable persisted ids and deterministic re-emit.
- **Provider/process lifetime** is request-local. Global slots may point to the
  foreground request but do not own cancellation truth.
- **MCP dispatch** uses a bijective exposed-name map and explicit pending
  settlement.
- **Durable file state** distinguishes missing/valid/corrupt and writes through
  serialized atomic replacement.
- **Retrieval degradation** is typed, traced, and visible; provider cardinality
  is validated before accepting results.
- **Prior art** is recorded per patch for LWW successor clocks, atomic local
  state writes, process cancellation, JSON-RPC shutdown, and hybrid-search
  degradation. Primary/official sources only for technical contracts.

## 5. Scope Exclusions & Stop Conditions

### Exclusions

- Chat compaction, storage quota UI, PDF annotations, web search, prompt-v2
  redesign, broad performance work, and unrelated dead-code cleanup remain
  separate roadmap items.
- Existing green v0.39 authored behavior is not rewritten merely because a
  different parser architecture is possible.

### Stop Conditions

- Stop before application code if the user does not approve this plan.
- Stop and revise as a Minor plan if any DB schema, public CLI/MCP/plugin field,
  persisted session DTO, or sync token format must change.
- Stop if source closure cannot distinguish shared from source-exclusive graph
  state using current ownership/dependency data.
- Stop if a valid remote timestamp is unbounded or cannot be ordered safely.
- Stop if an existing corrupt user file would need deletion or overwrite.
- Stop if three consecutive phase validations fail for the same unexplained
  reason.
- Stop if testbed validation would require reinitializing the active testbed or
  copying private external resources into a vault.
- Stop rather than rerun the consumed D2 holdout.

## 6. Evidence Ledger

- **Repository/schema reality**: clean start at `b567427`,
  `release/v0.39.0`, schema v13, manifests 0.39.0.
- **Current dirty worktree**: planning/roadmap/relay files only. No application,
  test, spec, guide, manifest, or user data changed before approval.
- **Rollback**:
  - PR #101 fixes are incremental commits after `b567427` and can be reverted
    independently;
  - each later patch branch starts from merged `master` and has its own rollback
    anchor;
  - no destructive production migration is planned.
- **Confirmed findings**: F01–F22 in
  `.agents/plans/02_v032_regression_evidence.md`.
- **Domain analyses**:
  - `A_v032_release_history_analysis.md`
  - `B_integrity_lifecycle_analysis.md`
  - `C_retrieval_provider_analysis.md`
  - `D_plugin_persistence_analysis.md`
- **Arena**: `.agents/plans/v032_regression_audit_arena/`.

## 7. Execution Phases

### P0 — Planning, Historical Inventory, And Baseline

Status: COMPLETE FOR PLANNING.

- Read repository rules, active plans, roadmap, relay, current specs, current
  implementation, and historical plans through Git.
- Inventory release PRs/commits/paths and freeze F01–F22.
- Reproduce source deletion and secret corruption in temporary state.
- Verify clean branch and existing green release evidence.

Gate: no application code changed.

### P1 — PR #101 Contract Clarification

Status: COMPLETE.

- Update `SCHEMA.md` and `SYSTEM_BEHAVIOR.md` for:
  - reconciliation of single-generation/no-source state;
  - exact audit membership at lifecycle admission;
  - strict-successor repair/retirement clocks;
  - dependency/revision-aware report invalidation.
- Update authored Markdown target parsing rules for balanced labels and
  single decoding.
- Update English USER/WORKFLOW guides first, then `_KR.md`.
- Update v0.39 changelog review notes.

Verify:

- docs/spec parity and `test_spec_sync.py`;
- no schema/title/version change.

### P2 — PR #101 Failing Oracles

Status: COMPLETE.

Add red tests for:

- source tombstone plus one future-clock generation/relation;
- relation omitted from current generation audit;
- equal-clock payload repair rejected by the peer;
- future-clock active relation/report retired locally;
- imported report already dependent on the winner edge;
- nested Markdown label;
- double-encoded space/slash targets.

Verify the new tests fail for the intended defects while current authored tests
remain green.

### P3 — PR #101 Root-Cause Fixes

Status: COMPLETE.

- Remove the generation-count early exit and reconcile all source groups.
- Enforce authored audit membership in lifecycle compilation.
- Add validated strict-successor revision calculation.
- Preserve monotonic clocks during relation/report retirement.
- Invalidate only reports older than or incompatible with the new winner
  dependency set.
- Add bounded nested-label scanning and one-pass target decoding.

Verify:

- authored topology, DB sync, graph lifecycle, report/search focused tests;
- Ruff and Mypy after each logical commit;
- adversarial two-/three-peer convergence and dry-run quiescence.

### P4 — PR #101 Full Validation And Delivery

Status: LOCAL VALIDATION COMPLETE — push and latest-head CI pending.

- Run full backend/plugin/static/build/audit gates.
- Validate on temporary DB/vault copies only.
- Inspect D2 tracked-file drift; update allowed hashes/evidence without rerun.
- Commit incrementally, push `release/v0.39.0`, update PR #101 description, and
  monitor latest-head CI.
- Merge remains a human action.

### P5 — v0.32.0–v0.34.1 Identity/Sync Audit And Source Lifecycle Patch

- Create a patch branch from merged `master`.
- Audit PRs #80–#86 plus #98 against current ownership/LWW paths.
- Docs-first/TDD-first implement F01 and F07:
  - complete source dependency closure;
  - serving queries require a live source;
  - deterministic post-publish projection recovery.
- Add local removal, imported tombstone, stale replay, shared support, and
  post-commit failure tests.
- Run two dry audit passes for these releases.

Expected version: next available v0.39.x patch.

### P6 — v0.32.1/v0.36.0 Persistence Audit And Durable-State Patch

- Audit storage relocation, serialized saves, facade moves, and later async
  hardening.
- Docs-first/TDD-first implement F14–F16:
  - missing/valid/corrupt state distinction;
  - byte-preserving corruption behavior;
  - serialized atomic session/secret/config writes;
  - recursive runtime credential redaction.
- Add concurrent/interrupted write and synced-session merge tests.

Expected version: next available v0.39.x patch.

### P7 — v0.35.0–v0.36.8 Provider/MCP Audit And Process-Lifecycle Patch

- Audit model/effort selection, plugin facade extraction, exception hardening,
  and PDF/Zotero/provider hotfixes.
- Docs-first/TDD-first implement F09–F13:
  - request-local cancellation;
  - non-streaming CLI model/PATH parity;
  - bijective MCP name dispatch;
  - pending rejection on shutdown;
  - command-class backend timeout/output limits.
- Validate sidebar + quick-query overlap, dismiss abort, CLI abort, MCP restart,
  tool-name collision, hung process, and long legitimate command behavior.

Expected version: next available v0.39.x patch.

### P8 — v0.33.0/v0.37.1 Retrieval And Prompt Audit Patch

- Audit embedding reuse, fail-closed exception paths, and provider-failure trace
  changes.
- Docs-first/TDD-first implement F08 and F19–F22:
  - explicit query-vector degradation;
  - exact provider result cardinality and finite values;
  - actual failover provider/model attribution;
  - numeric prompt version ordering.
- Validate lex fallback, vec-only failure, short/long provider output, NaN, and
  v9/v10 ordering.

Expected version: next available v0.39.x patch.

### P9 — v0.37.0–v0.39.0 Final Release-Chain Dry Pass

- Re-read every release row with the final code.
- Run two consecutive dry audit passes per release.
- Add newly confirmed findings to the smallest matching patch; never bury them
  in docs.
- Close only when:
  - no P0/P1 remains;
  - every P2 is fixed or explicitly queued with reason;
  - docs/code/tests agree on all changed contracts.

### P10 — Final Validation And Workflow Closure

For every patch release:

- use the repository `.venv-dev` through `scripts/backend-check`;
- run full backend/plugin/static/build/audit gates;
- run isolated current-contract testbed and Reference Mode smoke;
- update all manifests, CHANGELOG, ROADMAP, and RELAY;
- keep static spec titles on the v0.39 line for patch bumps;
- delete completed per-patch plans after Git preserves them;
- commit `chore(release): v0.39.Z`, push, open PR, and monitor CI.

After the last patch merges:

- delete this completed umbrella plan and evidence after preserving history;
- mark the v0.32.0+ audit closed in the stability roadmap;
- reset RELAY to IDLE only through the documented merged-release procedure.

## 8. Role Reviews

- **Lead architect**: proposed integrity-boundary patch releases.
- **Red team**: required cross-release symbol mapping, fault-transition tests,
  shared-state ownership proof, bounded clocks, and explicit corruption
  recovery.
- **Schema guardian**: confirmed current schema is sufficient; schema change is
  a stop condition.
- **Source-pair analyst**: required source deletion to close L1–L4/search while
  preserving independently supported shared artifacts.
- **System synthesizer**: accepted the patch chain with two-dry-pass release
  closure and no active-testbed mutation.

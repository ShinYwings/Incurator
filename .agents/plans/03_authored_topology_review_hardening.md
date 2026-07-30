# v0.39.0 Authored-Topology Review Hardening Master Implementation Plan

Date: 2026-07-30
Status: IMPLEMENTED — all local gates complete; latest-head CI pending

## 1. Objective

Make PR #101 safe to merge by closing confirmed parser, lifecycle, replica,
report, and search-freshness defects in the already-approved F9 behavior.

Definition of done:

- authored topology contains exactly what supported Markdown expresses;
- all current authored rows belong to the exact current generation;
- identical replica structure survives independent LWW clocks;
- topology additions/removals cannot leave stale served reports or authored
  search rows;
- no schema migration or public contract expansion is introduced.

## 2. Explicit Non-Goals

- No full CommonMark AST or new parser dependency.
- No fuzzy links, reference-style links, plugin citation grammar, or semantic
  alias merging.
- No broad inventory cache/performance redesign.
- No repair of the pre-existing extracted-KU/source-delete closure in this PR.
- No schema-v14 migration and no plugin wire change.

## 3. Strict Quality Conditions & Release Gates

- Every confirmed pre-fix reproduction has a failing test before application
  logic changes.
- Ambiguity always stops resolution; unsafe traversal and external URLs remain
  fail-closed.
- Authored relation membership is sorted and deterministic in generation audit.
- Sync passes with adversarial, intentionally divergent row/generation clocks.
- DB-only republish either carries byte-identical membership or retires it.
- New topology retires only endpoint-affected reports; removed topology retains
  exact dependency retirement.
- No orphan authored entity or retired authored relation search documents serve.
- Full backend pytest/Ruff/Mypy, plugin Vitest/build, npm audit, isolated
  testbed, graph audit, lint, and latest-head GitHub CI pass.

## 4. Locked Design Decisions (Arena Consensus)

- Length-preserving focused scanners replace destructive masking and the
  single-level Markdown destination regex.
- `.md` and `.markdown` share one Markdown-path predicate.
- Resolution stages are tri-state, and safe parent-relative normalization is
  lexical and vault-bounded.
- Existing generation `audit_json` records exact authored relation ids; there
  is no schema migration.
- Winner audit membership, not row timestamp, controls relation ownership after
  sync; lifecycle still uses the shared compiler.
- Added active edges invalidate reports by endpoint membership.
- Authored entity types materialize only when attached to active topology.
- Explicit source removal refreshes derived search.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: full source-deletion extracted closure, broad graph
  performance work, new syntax, schema changes, and plugin UI changes.
- **Stop** if exact winner membership cannot be represented in existing
  generation audit JSON.
- **Stop** if report freshness requires changing the public community-report
  schema rather than endpoint-based retirement.
- **Stop** if validation would modify the production vault or active testbed.

## 6. Evidence Ledger

- Clean review anchor: `d4420ea`; draft PR #101; schema v13.
- Confirmed results and user-vault measurement are in
  `.agents/plans/03_authored_topology_review_evidence.md`.
- Rollback is a normal revert of review commits on `release/v0.39.0`; no
  production data migration exists.

## 7. Execution Phases (TDD and CI at Each Phase)

- **P0 — Research & Measured Baseline** (**COMPLETE**)
  - Re-read specs/guides/implementation/tests and historical F9 plan.
  - Reproduce parser, lifecycle, sync, report, and search failures read-only.
  - Measure active user-vault patterns without mutation.

- **P1 — Contract Clarification** (**COMPLETE**)
  - Update system/schema/search specs and English guides first, then Korean
    pairs, for escape/masking, `.markdown`, safe parent paths, generation audit
    membership, and serving freshness.
  - Update v0.39 changelog review bullets.
  - Verify docs parity/spec sync.

- **P2 — Failing Regression Tests** (**COMPLETE**)
  - Add parser/resolver false-positive and false-negative cases.
  - Add `.markdown`, non-Markdown transition, and DB-only republish cases.
  - Add clock-skewed replica convergence.
  - Add pure-addition report retirement and authored search cleanup.
  - Capture the intentional red baseline.

- **P3 — Parser and Resolution Repair** (**COMPLETE**)
  - Implement length-preserving masks, bounded scanners, escape/tag validation,
    tri-state stages, safe parent normalization, and Markdown suffix predicate.
  - Verify focused authored-topology tests plus Ruff/Mypy.

- **P4 — Generation and Sync Repair** (**COMPLETE**)
  - Persist exact membership in generation audit.
  - Reconcile DB-only republish/non-Markdown transitions.
  - Reassign shared winner ids and retire loser-exclusive ids under sync.
  - Verify compiler/sync/audit tests plus Ruff/Mypy.

- **P5 — Serving Freshness** (**COMPLETE**)
  - Retire reports affected by newly active endpoints.
  - Filter orphan authored entities from search and rematerialize after source
    removal.
  - Verify report/search/router tests.

- **P6 — Full Validation** (**COMPLETE**)
  - Run all backend checks and plugin tests/build/audit.
  - Repeat isolated testbed compile/edit/sync/lint without changing the active
    testbed or production vault.
  - Re-review the complete diff and update D2 drift evidence for any tracked
    file changes without rerunning the consumed holdout.

- **P7 — Release Follow-up** (**IN PROGRESS**)
  - Update evidence, roadmap, and RELAY.
  - Delete completed review-plan artifacts after all gates pass.
  - Commit incrementally, push to the existing branch/PR, and wait for
    latest-head CI.

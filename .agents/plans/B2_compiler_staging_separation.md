# Plan B2 Master Implementation Plan — Compiler Staging/Authoritative Row Separation (§26.3 enforcement)

Date: 2026-06-13
Status: DRAFT — Arena concluded (`compiler_staging_separation_arena/`); awaiting user approval before code.
Origin: Plan B P6 review Flaw 3 (`.agents/USER_REPORT.md`). User chose the
staged-row-separation (copy-on-stage) approach.

## Strict Quality Condition

- A staged generation's `knowledge_units` / `claim_supports` are NEVER reachable
  by query, evidence, search, or any served ATM projection until that generation
  publishes; the compiler audit asserts zero staged rows in any served surface.
- Publish flips DB rows + dependency closure + ATM projections + search
  materialization together; discard removes all staged rows and leaves the prior
  authoritative generation and its served state byte-identical.
- Every P6 oracle stays green (unchanged-rebuild idempotency, failed-compile-no-
  partial-publish, F7 reconciliation, compiler audit + lint surface, F10
  hydration). Full local CI (pytest + ruff + mypy + plugin vitest) passes.
- No change to the retrieval/query read path or the D2-holdout-pinned files
  (`engine.py`/`lexical.py`/`fusion.py`/`evaluation.py`/`chunking.py`/`embedding.py`).

## Locked Design Decisions (Arena Consensus)

Visibility is gated at **write/materialization time, not read time** (red-team
A2). Detail in `compiler_staging_separation_arena/03_synthesis.md`:

1. **Staged units are stored but never materialized.** A staged generation's
   `knowledge_units` rows exist (`generation_id=gen_S`, gen `staged`) but the
   compiler emits NO ATM page, graph linkage, or search doc for them while
   staged. Serving READ paths are therefore unchanged.
2. **Emit/materialize only from authoritative generations, after publish, from
   the DB** (red-team A1). Projections are disposable → on FS/materialize failure
   they re-emit from the authoritative DB. No staging dir; no split-brain.
3. **Eligibility splits in two:** `list_serving_units(db, source_id=None)`
   (authoritative ∧ verified ∧ not-retired) for serving/materialization;
   `list_generation_units(db, gen_id)` (one generation) for the compiler's staged
   build. The raw `materializer.py` KU query and `reemit_projections` move to the
   serving variant; `compile_source_l2`'s build + `recompile_source` use the
   generation variant.
4. **Stable-id reuse stays at STAGE time** (red-team A3), generation-scoped, via
   the existing `reconcile_source` predicate (semantic-hash candidate + exact
   normalized statement), so the L2→L3/L4 closure is built against final ids.
5. **Publish = single DB transaction:** flip gen_S→authoritative, gen_A→discarded,
   retire gen_A's unmatched rows; then re-emit ATM + graph + search from the
   authoritative DB.
6. **Migration (red-team A4):** deterministic synthetic generation
   `GEN-mig-<source_id>` (status authoritative) owns each legacy source's verified
   `generation_id IS NULL` units. NULL thereafter = not a Plan-B claim (no
   permanent NULL escape hatch — repo invariant).
7. **Invariant (red-team A5):** an authoritative generation MAY contain
   non-verified units (stored + audited, never served). Served = authoritative-gen
   ∧ verified ∧ not-retired — visibility no longer keys on `support_status` alone.
8. **Publish guards (red-team R6/R7):** refuse to publish a zero-unit staged
   generation when a non-empty authoritative generation exists; the unchanged-
   content short-circuit first verifies the authoritative materialization exists
   (repairs a half-failed prior publish idempotently).

## Evidence Ledger

### Current Repository & Schema Reality (verified 2026-06-13 @ HEAD `171ea38`)
- `list_eligible_knowledge_units` (db.py:1859) callers: `compile.py:263` (ATM emit
  in compile — COMPILER), `compile.py:438` (`recompile_source` verified_ids —
  COMPILER), `compile.py:556` (`reemit_projections` — SERVING/rebuild).
- `materializer.py:130-137` reads `knowledge_units WHERE retired_at IS NULL AND
  support_status='verified'` DIRECTLY (not via list_eligible) — the SERVING search
  materialization path; must become authoritative-only.
- No serving read of `knowledge_units` exists in `retrieval/evidence.py` /
  `query.py` outside materialized search docs + ATM pages (verified by grep) — so
  gating at materialization fully covers serving.
- `compiler_generations` already exists (P3); `recompile_source` already
  short-circuits on unchanged `content_hash` and discards-on-failure (P6/Flaw 2).
- `search_documents` PK `(record_type, record_id)`; NO generation column (and the
  adopted design adds none).

### Current Dirty Worktree
- `scratch.py` (user's, untracked, pre-existing) — do not touch.
- P6 + review fixes are committed (`eb59a97`..`171ea38`); branch
  `feature/plan-b-math-distillation`.

### Rollback Requirements
- Back up `state.sqlite` before the migration (reuse
  `.agents/backups/b-pre-implementation-state.sqlite` rehearsal procedure, §26.6).
- The migration is additive + deterministic; rehearse on a disposable copy first.
- D2 holdout: this plan must NOT touch the pinned retrieval files; if it does, the
  holdout is invalidated (cannot re-arm a ranking-path change).

## Execution Phases (Follow TDD and CI at each phase)

- **P1 — Docs-first contract.** Update SCHEMA §20.3/§20.5 (invariant #7: served =
  authoritative ∧ verified ∧ not-retired; audit asserts zero staged rows served),
  SYSTEM_BEHAVIOR §26.3 (copy-on-stage emit-after-publish, publish guards),
  SEARCH_ENGINE §10.1 (materialize authoritative-only). EN→KR guides if behavior
  surfaces. Verify: specs/tests-to-write agree; no code change.
- **P2 — Failing tests.** Oracles: staged units invisible to search/evidence/ATM;
  publish emits + materializes; discard leaves prior served state byte-identical;
  authoritative-gen-with-unchecked-unit is stored-not-served; zero-unit publish
  guard. Verify: new tests fail for the intended reasons; suite otherwise green.
- **P3 — Eligibility split + migration.** Add `list_serving_units` /
  `list_generation_units`; migrate legacy NULL units to `GEN-mig-<source_id>`;
  point `materializer.py` + `reemit_projections` at the serving variant. Verify:
  migration rehearsal (§26.6) + focused pytest + ruff + mypy.
- **P4 — Copy-on-stage compile.** Rework `compile_source_l2` + `recompile_source`:
  stage units (generation-scoped build, no emit), reconcile-at-stage, audit,
  atomic publish, post-publish emit/materialize from DB, discard cleans staged
  rows; publish guards. Verify: all P6 oracles + new P2 oracles green; ruff; mypy.
- **P5 — Testbed + full CI.** `VAULT_ROOT=testbed wiki update|lint`; confirm
  staged invisibility end-to-end; full pytest + ruff + mypy + plugin vitest.
- **P6 — Release.** Version bump (continues the v0.8.0 line), CHANGELOG, delete
  this plan, release commit, PR. (Folds into the Plan B v0.8.0 release if B has
  not shipped yet; otherwise a +0.0.1 follow-up.)

## Quality Gates
- 0 staged rows reachable by any served surface (asserted by the audit + a test).
- Publish/discard atomicity proven by failure injection at each boundary.
- Unchanged-rebuild idempotency + F7 reconciliation oracles still green.
- Retrieval read path + D2-pinned files byte-unchanged.

## Explicit Non-Goals
- L3/L4 (community report / synthesis) generation isolation — Plan C.
- Multi-writer / concurrent-compiler safety (single-process SQLite assumed).
- Retrieval ranking/fusion changes.

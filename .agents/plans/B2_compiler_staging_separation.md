# Plan B2 Master Implementation Plan — Compiler Staging/Authoritative Row Separation (§26.3 enforcement)

Date: 2026-06-13
Status: DRAFT — Arena concluded + 2nd review round folded in
(`compiler_staging_separation_arena/`, incl. `04_critique_reviewer.md`); awaiting
user approval before code.
Origin: Plan B P6 review Flaw 3 (`.agents/USER_REPORT.md`). User chose the
staged-row-separation (copy-on-stage) approach. A second review round corrected
three fatal flaws in the v1 plan (PK paradox → publish-time reconcile; graph
leakage → graph upsert deferred to publish txn; zero-unit guard removed).

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

1. **Staged units are stored with TEMPORARY ids and never materialized.** A
   staged generation's `knowledge_units` rows exist with temp ids
   (`generation_id=gen_S`, gen `staged`) but the compiler emits NO ATM page, NO
   graph upsert, and NO search doc for them while staged. **Graph extraction
   (LLM) runs during staging but its entities/relations are NOT upserted** — they
   are serialized (in memory / `compiler_generations.audit_json`) and persisted
   only inside the publish transaction (resolves 2nd-review Flaw 2: `graph_*`
   tables have no `generation_id`, so an in-staging upsert would leak past the
   gate and dangle on discard). Serving READ paths are unchanged.
2. **Emit/materialize only from authoritative generations, after publish, from
   the DB** (red-team A1). Projections are disposable → on FS/materialize failure
   they re-emit from the authoritative DB. No staging dir; no split-brain.
3. **Eligibility splits in two:** `list_serving_units(db, source_id=None)`
   (authoritative ∧ verified ∧ not-retired) for serving/materialization;
   `list_generation_units(db, gen_id)` (one generation) for the compiler's staged
   build. The raw `materializer.py` KU query and `reemit_projections` move to the
   serving variant; `compile_source_l2`'s build + `recompile_source` use the
   generation variant.
4. **Stable-id reconciliation is DEFERRED to PUBLISH time** (2nd-review Flaw 1 —
   stage-time reuse is a PK paradox: the DB cannot hold both authoritative `KU-1`
   and staged `KU-1`). Staged units carry temp ids; the atomic publish
   transaction runs the reconcile (existing semantic-hash + exact-normalized-
   statement predicate): for an unchanged claim it merges the temp row into the
   stable `KU-1` row, sets `KU-1.generation_id=gen_S`, **rewrites every downstream
   reference from the temp id to the stable id** (`graph_entities.knowledge_unit_ids`,
   `graph_relations.knowledge_unit_ids`, `claim_supports.knowledge_unit_id`,
   `artifact_dependencies`, `dag_edges`), and deletes the temp row. Changed/new
   claims keep their (now-permanent) temp-minted id; removed prior claims are
   retired.
5. **Publish = single DB transaction:** reconcile temp→stable (Item 4) → upsert
   the serialized graph entities/relations against FINAL stable ids (Item 1) →
   flip gen_S→authoritative, gen_A→discarded, retire gen_A's unmatched rows.
   ONLY AFTER the DB commits: re-emit ATM + materialize search from the
   authoritative DB (re-emittable on FS failure, Item 2).
6. **Migration (red-team A4):** deterministic synthetic generation
   `GEN-mig-<source_id>` (status authoritative) owns each legacy source's verified
   `generation_id IS NULL` units. NULL thereafter = not a Plan-B claim (no
   permanent NULL escape hatch — repo invariant).
7. **Invariant (red-team A5):** an authoritative generation MAY contain
   non-verified units (stored + audited, never served). Served = authoritative-gen
   ∧ verified ∧ not-retired — visibility no longer keys on `support_status` alone.
8. **No zero-unit publish guard** (2nd-review Flaw 3). A SUCCESSFUL extraction
   that yields zero units is the correct, deterministic representation of an
   emptied / non-claim-bearing source and MUST publish — which retires the prior
   authoritative units (otherwise the index serves deleted claims forever). A
   FAILED extraction already returns `ku_result.ok=False` and errors without
   publishing, so this does not reintroduce silent loss; a zero-unit publish that
   retires N>0 prior units is recorded as a non-blocking audit log only. The
   unchanged-content short-circuit still first verifies the authoritative
   materialization exists (repairs a half-failed prior publish idempotently, R6).

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
- **P2 — Failing tests.** Oracles: staged units (+ their graph entities) invisible
  to search/evidence/ATM; a failed/discarded staged compile leaves NO graph
  entity/relation behind (Flaw 2); publish emits + materializes + persists graph
  against stable ids; discard leaves prior served state byte-identical; temp→stable
  id rewrite keeps `graph_entities`/`graph_relations`/`claim_supports`/
  `artifact_dependencies`/`dag_edges` consistent (Flaw 1); a SUCCESSFUL zero-unit
  compile publishes and retires the prior units (Flaw 3);
  authoritative-gen-with-unchecked-unit is stored-not-served. Verify: new tests
  fail for the intended reasons; suite otherwise green.
- **P3 — Eligibility split + migration.** Add `list_serving_units` /
  `list_generation_units`; migrate legacy NULL units to `GEN-mig-<source_id>`;
  point `materializer.py` + `reemit_projections` at the serving variant. Verify:
  migration rehearsal (§26.6) + focused pytest + ruff + mypy.
- **P4 — Copy-on-stage compile.** Split `graph_index.extract_entities_and_relations`
  into extract (LLM, staging, temp ids, serialized) vs persist (publish txn,
  rewritten to stable ids). Rework `compile_source_l2` + `recompile_source`:
  stage units with temp ids (generation-scoped build, NO emit/upsert), validate,
  audit; on pass run the atomic publish txn (temp→stable reconcile + downstream
  ref rewrite → graph persist against stable ids → flip gen_S authoritative /
  retire gen_A) then post-publish emit ATM + materialize search from the
  authoritative DB; on any failure discard ALL staged rows (units + claim_supports;
  no graph/ATM/search were written). No zero-unit guard. Verify: all P6 oracles +
  new P2 oracles green; ruff; mypy.
- **P5 — Testbed + full CI.** `VAULT_ROOT=testbed wiki update|lint`; confirm
  staged invisibility end-to-end; full pytest + ruff + mypy + plugin vitest.
- **P6 — Release.** Version bump (continues the v0.8.0 line), CHANGELOG, delete
  this plan, release commit, PR. (Folds into the Plan B v0.8.0 release if B has
  not shipped yet; otherwise a +0.0.1 follow-up.)

## Quality Gates
- 0 staged rows (units, claim_supports, graph entities/relations) reachable by
  any served surface (asserted by the audit + a test).
- A discarded staged compile leaves 0 orphan graph entities/relations and 0
  dangling unit references (Flaw 2 gate).
- temp→stable id rewrite at publish leaves 0 dangling references in
  `graph_*`/`claim_supports`/`artifact_dependencies`/`dag_edges` (Flaw 1 gate).
- A successful zero-unit compile publishes and retires the prior units (Flaw 3).
- Publish/discard atomicity proven by failure injection at each boundary.
- Unchanged-rebuild idempotency + F7 reconciliation oracles still green.
- Retrieval read path + D2-pinned files byte-unchanged.

## Explicit Non-Goals
- L3/L4 (community report / synthesis) generation isolation — Plan C.
- Multi-writer / concurrent-compiler safety (single-process SQLite assumed).
- Retrieval ranking/fusion changes.

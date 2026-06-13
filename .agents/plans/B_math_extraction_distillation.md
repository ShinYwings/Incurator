# Program 2B Master Implementation Plan — Source-Pair, Math Extraction, And Claim-Level Distillation Integrity

Date: 2026-06-11
Status: DRAFT — dedicated Arena concluded; awaiting Program 1 completion and user approval before implementation
Arena: `.agents/plans/math_extraction_distillation_arena/`

## 0. Objective And Program Boundary

Program 2B is the first Evidence Compiler Integrity release. It makes
Markdown/PDF source truth compile into stable, minimal, claim-level grounded L2
knowledge without formula loss, unsupported broad-span grounding, duplicate
accumulation, stale records, or partial authoritative publishes.

This plan is intentionally independent from graph-quality Plan C. B defines and
publishes the claim/support generation that C must consume. B does not implement
entity resolution, relation denoising, hierarchy, retrieval tuning, agent
serving, or quota.

## Strict Quality Condition

- Every active `source_supported` knowledge unit has at least one verified
  minimal support record whose evidence hash matches current source truth.
- Every central-formula gold claim preserves or exactly references the central
  formula; no hallucinated recovery is silently accepted.
- Raw parser/source evidence is immutable; recovery is additive and labeled.
- Unchanged compilation produces identical authoritative claim/support ids,
  hashes, dependency closure, and counts.
- Edit/delete/split invalidates and regenerates only the expected dependency
  closure.
- Failed compilation publishes no partial authoritative DB, projection, or
  search-derived state.
- No Plan-B-owned source-pair/L2 or non-graph generated-claim path may substitute
  a broad all-upstream-span set for missing claim-level support. Plan-C-owned
  graph/community-report fallbacks are measured and handed off explicitly.

## Locked Design Decisions (Arena Consensus)

1. `source_spans` remains atomic L1 evidence identity. Real span ids are
   necessary but not sufficient proof of claim support.
2. Raw source evidence remains immutable. Formula recovery is an additive
   candidate with locator/crop hash/provider/model/confidence/validator lineage.
3. Recovery runs only after a measured `fragmented`, `image_only`, or
   `parser_omitted` loss verdict; every-page VLM processing is rejected.
4. Recovery lifecycle is `candidate`, `reviewed`, or `rejected`; parseable LaTeX
   alone cannot mark a candidate verified.
5. Each source-supported claim records minimal support roles/statuses. Existing
   rows migrate as `unchecked`, never silently `verified`.
6. Claim semantic hashes support reconciliation candidates only and cannot
   automatically merge materially different claims/equations.
7. Central formulas may live in concise claim text or an exact linked formula
   evidence record. Incidental omission is allowed only with an auditable reason.
8. Compiler writes use staged generations. A generation becomes authoritative
   only after required rows, dependencies, projections, and search-derived state
   validate.
9. Downstream compiler prompts receive claim-scoped evidence rather than a broad
   source/community span pool.
10. Deterministic/human-labeled gold fixtures are release oracles; model support
    judges are secondary.
11. Source edit/delete/split reconciliation retires/removes stale source-derived
    artifacts and audits the complete downstream dependency closure.
12. B does not implement Plan C graph resolution/hierarchy, Program 3 retrieval/
    serving, or vault quota.

## Dependencies And Approval Gates

### Hard Prerequisites

- Program 1 is merged into `master`.
- Program 1 has approved:
  - Failure Atlas with reproduced source-pair/compiler failures;
  - Plan E research decision package and adopt/benchmark/reject records;
  - Evaluation Specification with minimal-support and formula-centrality labels;
  - exact source locator and evidence identity contract;
  - compiler/query observability needed to measure B;
  - migration and rollback specification baseline.
- Active testbed scenario is confirmed; `complex_math_backprop` may be rewritten
  but must not be blindly assumed to be the only active scenario.

### Ordering

```text
Program 1 merged
  -> B specs and migration contract approved
  -> B implemented, validated, merged
  -> C implementation begins
  -> Program 3 begins only after C
```

### Mandatory Stop

Stop before code after P0/P1 specification artifacts are written and request
user approval under the Universal Strict Workflow.

## Evidence Ledger

### Current Repository & Schema Reality

- Planning inspection SHA: `12cc63ec3c43cfdf2049215f314876842b079f2d`
  on `feature/editor-latex-copy`; implementation must refresh from merged Program
  1 `master`.
- `source_spans` deduplicates by `(source_id, content_hash)`, stores a short
  preview, and accepts metadata.
- L1 preserves explicit `$$...$$` blocks only when parser output contains them.
- L2 checks allowed span ids but not minimal support/entailment.
- `upsert_knowledge_unit()` creates new ids by default; authoritative rebuild
  identity and stale reconciliation are undefined.
- `compile_source_l2()` makes persistent writes across multiple stages before all
  stages validate.
- Graph extraction may truncate a long formula-bearing statement.
- Report/synthesis generation can fall back to broad upstream span sets.

### Current Dirty Worktree

- The planning worktree contains pre-existing shared/unrelated changes.
- This plan and Arena modify only user-assigned paths.
- No implementation branch, specs, guides, tests, ROADMAP, RELAY, umbrella plan,
  or production code was changed.

### Rollback Requirements

Immediately before coding:

1. Create a fresh branch from merged Program 1 `master`; update RELAY then.
2. Record exact SHA, schema/version, providers/models, active scenario, baseline
   compiler audit, and baseline duplicate/stale/formula metrics.
3. Back up `state.sqlite`; verify restoration before migration.
4. Rehearse additive migration on a disposable copy.
5. Preserve clean rebuild from source truth.
6. Keep prior authoritative compiler generation until the staged new generation
   passes audit and publishes.
7. If migration or audit fails, restore DB backup, discard staged generation,
   re-emit projections/search from the prior authoritative generation, and return
   to planning after three repeated QA failures.

### Evidence Ledger Refresh Deliverable

Before implementation, create the required coding-time evidence ledger from the
approved Program 1 template. The Arena ledger is a planning snapshot, not the
final rollback record.

## Target Contract And Candidate Schema

Final names are frozen in specs before code. The Arena recommends:

```sql
ALTER TABLE knowledge_units ADD COLUMN semantic_hash TEXT;
ALTER TABLE knowledge_units ADD COLUMN support_status TEXT NOT NULL DEFAULT 'unchecked';
ALTER TABLE knowledge_units ADD COLUMN support_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE knowledge_units ADD COLUMN formula_status TEXT NOT NULL DEFAULT 'not_applicable';
ALTER TABLE knowledge_units ADD COLUMN retired_at TEXT;

CREATE TABLE claim_supports (
  knowledge_unit_id TEXT NOT NULL,
  source_span_id TEXT NOT NULL,
  support_role TEXT NOT NULL,
  support_status TEXT NOT NULL,
  support_reason TEXT NOT NULL DEFAULT '',
  evidence_hash TEXT NOT NULL,
  validator_trace_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (knowledge_unit_id, source_span_id, support_role)
);
```

Normalize formula recovery candidates only if Program 1 measurements prove
multiple-attempt lifecycle/indexed audit requirements. Otherwise use structured
`source_spans.metadata` with an approved schema.

## Migration And Rollback Plan

### Migration Strategy

1. Add schema fields/tables forward-only.
2. Backfill existing knowledge units as `support_status='unchecked'`; do not
   infer minimal support or formula verification.
3. Run a read-only legacy compiler audit and record invalid/missing/stale rows.
4. Build a new staged compiler generation from source truth under new prompt/
   support contracts.
5. Compare source/claim coverage, ids/hashes, counts, projections, dependencies,
   search materialization, and downstream invalidation.
6. Publish the new generation only after quality gates pass.
7. Retire old source-derived generations according to the approved spec; do not
   delete source truth.

### Rollback

- Before publish: discard staged rows/files and retain old authoritative state.
- After publish but before release: restore DB backup and regenerate disposable
  projections/search.
- After release: patch forward unless corruption requires the documented safe
  Git/DB rollback; never destructive-reset shared history.

## Execution Phases (Follow TDD And CI At Each Phase)

### P0 — Program Setup And Measured Baseline

- Start fresh branch from merged Program 1 `master`.
- Refresh evidence ledger and active scenario.
- Run Program 1 compiler/failure-atlas measurements for formula loss,
  wrong-real-span support, unchanged rebuild, edit/delete/split, and failed
  compile.
- Classify each failure boundary before approving recovery work.

Verify:

- No behavior change.
- Baseline fixtures and command outputs are reproducible.
- Every concern is reproduced, disproven, accepted, or scheduled.

### P1 — Docs-First Contract And Migration Specification

- Update all affected static specs synchronously:
  `SCHEMA.md`, `SYSTEM_BEHAVIOR.md`, `PLUGIN_SCHEMA.md` only if plugin audit
  surfaces change, and `SEARCH_ENGINE_SCHEMA.md`.
- Update English guides first, then faithful `_KR.md` counterparts:
  `USER_GUIDE`, `WORKFLOW_GUIDE`, `MCP_USER_GUIDE`,
  `AGENT_WORKFLOW_GUIDE`, and any changed plugin guide.
- Freeze source-pair/support/recovery/generation/reconciliation/audit contracts.
- Write migration rehearsal and rollback acceptance criteria.
- Stop for user approval before application code.

Verify:

- Specs, guides, plan, tests-to-be-written, and migration names agree.
- No code behavior change.

### P2 — Failing Gold Tests And Compiler Audit Oracles

- Add deterministic fixtures for preserved/fragmented/image-only/omitted math,
  central/incidental formulas, wrong real citations, minimal multi-span support,
  contradictions, long formula tails, unchanged rebuild, edit/delete/split, and
  prompt/provider failure.
- Add human-labeled holdout support/centrality fixtures from Program 1.
- Add failing compiler-audit tests that traverse active L2-L4 claims to exact
  support.
- Rewrite stale `complex_math_backprop` assertions around current DB-native
  L1-L4 and Reference Mode behavior.

Verify:

```bash
uv run --directory backend pytest -q <focused B tests>
uv run --directory backend ruff check src/
```

Expected: new behavior tests fail for the intended reasons; unchanged legacy
tests remain green.

### P3 — Additive Schema And Support Lifecycle

- Implement additive migration and DB helpers for claim support/recovery/
  generation lifecycle.
- Update DB sync/export/import and inspection surfaces for new authoritative
  records.
- Enforce evidence-hash freshness and source-supported eligibility.
- Backfill legacy rows as unchecked in migration tests.

Verify:

- Fresh DB, migrated DB, export/import, backup/restore, and clean rebuild tests.
- No existing row is silently verified.
- Focused pytest + ruff + mypy pass.

### P4 — Claim Extraction, Minimal Support, And Stable Reconciliation

- Version the knowledge-unit prompt contract for minimal support and formula
  centrality.
- Implement deterministic claim normalization/fingerprint candidate logic.
- Implement support validation with deterministic gold checks and secondary
  calibrated model validation.
- Reconcile unchanged/changed/deleted/split source claims and retire stale units.
- Prevent retired/unchecked-disallowed claims from feeding downstream stages.

Verify:

- Wrong real citations fail.
- Unchanged rebuild preserves authoritative ids/hashes/counts.
- Edit/delete/split changes only expected closure.
- Focused pytest + ruff + mypy pass.

### P5 — Selective Formula Recovery And Downstream Preservation

- Implement loss-boundary classification covering BOTH absence and corruption:
  a region is a recovery candidate when parser/raw-text/current-extraction
  either MISS it entirely (`image_only`, `parser_omitted`) OR extract a
  STRUCTURALLY-INVALID rendering of it (`fragmented` — present but garbled,
  e.g. a PDF text-layer that drops `\nabla`/superscripts or splits a `$$`
  block). The `fragmented` trigger is a structural-validation failure of the
  extracted formula against the rendered region, NOT total absence. (Parse
  fidelity is a source-type problem: Markdown `.md` carries true LaTeX and is
  faithful passthrough; PDFs render math as glyphs and cannot yield LaTeX from
  the text layer, which is why selective visual recovery — not a base-parser
  rewrite — is the fix. A VLM routing placeholder already exists at
  `parsers/pdf.py`.)
- Route P4's `formula_status='uncertain'` verdicts into this classification: an
  uncertain central formula (a claim-vs-span ordered-token mismatch on a lossy
  source, §26.1) is the upstream signal that the L1 span may be a corrupt
  rendering. Validated recovery re-validates the owning claim (`uncertain` →
  `verified` against the recovered evidence, or `missing` if unrecoverable); it
  never silently flips a claim verified without a validator verdict. This is the
  intended P4→P5 staging: P4 grounding is parse-agnostic and degrades to
  `uncertain` (never a wrong verify) on lossy sources; P5 recovery is what
  reduces those uncertains and closes the source-fidelity gap.
- Implement optional recovery adapter only for approved loss classes.
- Store locator/crop/model/confidence/validator lineage.
- Preserve central formulas through graph input and search materialization;
  remove destructive central-formula truncation.
- Record explicit missing/uncertain/incidental outcomes.

Verify:

- Provider-free classifier/validator tests pass.
- Mocked recovery tests never overwrite raw evidence.
- Central formula recall meets approved threshold with zero silent hallucinated
  replacements.
- Focused pytest + ruff + mypy pass.

### P6 — Staged Atomic Publish And Full Dependency Reconciliation

- Stage source compile generations and validate before authoritative publish.
- Publish DB rows, dependency state, projections, and search-derived state as one
  compiler generation contract.
- Remove broad all-upstream-span fallback from source-pair/L2 and non-graph
  generated claims owned by Plan B. Plan C owns community-report and graph-derived
  fallback removal.
- Invalidate/reconcile full downstream closure.
- Inject failures at every publish boundary.

Verify:

- Failure injection leaves prior authoritative generation unchanged.
- Compiler audit reports no orphan/stale/Plan-B-owned broad-fallback active
  artifacts and explicitly assigns graph/report fallback findings to Plan C.
- One-source edit regenerates only approved dependency closure.
- Focused pytest + ruff + mypy pass.

### P7 — Current Testbed And End-To-End Compiler Audit

- Initialize the confirmed active scenario; rewrite/run
  `complex_math_backprop` as the math-specific scenario.
- Validate Markdown, local PDF, and Reference Mode external PDF behavior.
- Run provider-backed extraction/recovery where available; otherwise run all
  deterministic/local simulator gates and document the exact blocker.
- Confirm no source/reference files are autonomously edited.

Verify:

```bash
VAULT_ROOT=testbed wiki status
VAULT_ROOT=testbed wiki add
VAULT_ROOT=testbed wiki update
VAULT_ROOT=testbed wiki lint
```

Plus approved compiler-audit and formula/support scenario commands.

### P8 — Sequential Role Reviews

Run and record:

1. `coder_engineer`: scope and implementation against plan.
2. `peer_reviewer`: atomicity, error paths, coupling, partial publish risks.
3. `schema_guardian`: schema/source truth/ID/layer contracts and migration.
4. `source_pair_analyst`: minimal support, formula lifecycle, no broad fallback.
5. `qa_runner`: focused/full CI, migration, failure injection, testbed.
6. `docs_sync_manager`: specs/guides English→Korean parity.
7. `legacy_sweeper`: stale EXH/qmd assumptions, orphan APIs/tests/comments.

Any non-trivial review finding re-enters capture → plan → approval before code.

### P9 — Full Local CI And Release Gates

```bash
export UV_PROJECT_ENVIRONMENT="$(git rev-parse --show-toplevel)/.venv"
uv run --directory backend pytest -q
uv run --directory backend ruff check src/
uv run --directory backend mypy src/
npx vitest run -c ./plugin/vitest.config.ts
```

Also run migration rehearsal, compiler audit, active testbed, and exact approved
Program 1/B quality suite.

### P10 — Release Completion

- Clean resolved roadmap/report items only under the Universal Strict Workflow.
- Bump `backend/pyproject.toml`, `plugin/package.json`, and
  `plugin/manifest.json` to one agreed version.
- Update `CHANGELOG.md`.
- Delete implemented active plan files only at the workflow's required step.
- Final commit: `chore(release): vX.Y.Z`.
- Push branch and open detailed PR. Do not start C until B is merged.

## Quality Gates

### Claim And Evidence

- 100% gold `source_supported` claims have verified minimal support.
- 0 wrong-real-span gold citations accepted.
- 0 active broad all-upstream-span fallback claims in Plan-B-owned source-pair,
  L2, and non-graph generated claims; graph/report fallbacks are recorded as
  blocking Plan-C inputs.
- 100% active support evidence hashes match current source spans.
- Unsupported/uncertain claims are explicitly labeled and excluded where the
  contract requires verified support.

### Math

- Central-formula recall meets the Program 1 approved threshold.
- 0 silent hallucinated/recovered-formula replacements.
- 100% recovery candidates carry exact locator/crop hash/provider/model/
  confidence/status lineage.
- Incidental omissions carry approved reason codes.

### Compiler Integrity

- Unchanged rebuild yields identical authoritative records/dependency hashes and
  no count amplification.
- One-source edit/delete/split changes only expected closure.
- Failed compile leaves no partial authoritative state.
- Compiler audit finds 0 active orphan/stale support/dependency records.
- DB backup/restore and additive migration rehearsal pass.

### CI And Testbed

- Full local CI passes.
- Current math/source-pair testbed passes, or external provider blocker is
  explicitly documented while all lower-level gates pass.

## Required Documentation Surfaces

- `docs/specs/curator_schema/SCHEMA.md`
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`
- `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`
- `docs/specs/plugin_schema/PLUGIN_SCHEMA.md` only if exposed audit contracts
  change
- Relevant English guides first, then matching `_KR.md` guides
- Prompt contract/evaluation documentation and current scenario plan

## Explicit Non-Goals

- Entity alias/merge, relation support aggregation, or hierarchy implementation.
- Retrieval ranking/routing/context service changes.
- Quota, storage UI, or admission control.
- Automatic source/reference edits.
- Whole-document/every-page VLM processing.

## Stop Conditions

- Stop now: planning only; no implementation is authorized.
- Stop before code until Program 1 is merged and P1 contracts are approved.
- Stop recovery work without measured parser/L1 loss.
- Stop publish work if projection/search state cannot participate in generation
  rollback.
- Stop release if any claim-support, central-formula, idempotency, atomicity,
  reconciliation, migration, CI, or testbed gate fails.
- After three repeated QA failures, activate `rollback_strategist`, restore the
  last stable state, and return to planning.

---

## Plan E P7 Research Handoff (2026-06-12)

Source: `backend/research_spikes/reports/p7.md`, `backend/research_spikes/manifests/p7.yml`.
Binding specification requirements handed off at Plan E P8; adoption still
flows through this plan's own phases, benchmarks, and gates.

### Adopted Contract: Formula-Preserving Distillation (`adopt-contract`, confirmed at P7)

Downstream distillation MUST NOT silently remove a formula that is present in
authoritative extraction. Wave D FR01 proved current distillation drops a
formula that current extraction contains; the FR05 holdout confirmed
distillation introduced nothing absent from extraction. Any distillation stage
in this plan must carry an explicit formula-preservation check (extraction
formula set ⊆ distillation-visible evidence, or an explicit recorded
exception), and visual recovery is NOT a substitute for this boundary.

### Contract Candidates: Selective Formula Recovery (`benchmark-later`)

If/when this plan benchmarks visual formula recovery, only the following
invariants are pre-accepted as contract candidates (mechanism adoption needs
this plan's own measured win):

- Recovery runs only on proven-loss regions (parser AND raw-text AND current
  extraction all missing the region) — never whole-corpus by default.
- Recovered content is stored separately from raw evidence and never
  overwrites it.
- Confidence below the acceptance threshold stays explicitly uncertain and is
  excluded from served formulas.
- Every recovered item carries an exact source locator (source id, page,
  region) and the source page hash.
- A changed page hash invalidates exactly that page's recovery; a failed
  refresh must be detectable as stale (Wave D regression proof).

REJECTED DEFAULT: whole-corpus heavy visual recovery (`7x` measured proxy
cost; reaffirmed on the FR05 holdout, 10 vs 0).

### Benchmark Requirements Inherited: Context-Enriched Chunks (`benchmark-later`)

If this plan's projection/search-state work evaluates generated retrieval
context, the Wave A cache/invalidation assumptions are the benchmark contract:
per-chunk cache keyed by span content hash + prompt/model version; source-edit
invalidation of the edited chunk plus re-queue of sibling chunks;
deletion-driven invalidation (generated context never outlives its raw span);
full-rebuild cost measured for prompt/model version changes. Generated context
must remain visibly non-authoritative, preserve exact raw-span linkage, beat a
deterministic heading control, and pass direct-factual non-regression.

### Plan D2 Program-1 Handoff (v0.7.0)

Consume `docs/specs/failure_atlas/PROGRAM_HANDOFFS.md` and the frozen F6/F7/F10
oracles. Every evaluation report must use the D2 per-family fine-grained metric
contract; aggregate-only and model-judge-only gates are prohibited.

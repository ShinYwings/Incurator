# Program 1D Master Implementation Plan: Current-System Failure Atlas And Quality Observatory Groundwork

Date: 2026-06-11
Status: APPROVED - D2 execution authorized by the user on 2026-06-12
Arena: `.agents/plans/current_system_failure_atlas_arena/`
Umbrella: `.agents/plans/03_rag_knowledge_quality_stabilization.md`

## 0. Purpose And Program Position

Plan D is the executable owner of Program 1's diagnosis and Quality Observatory.
It runs in two releases around Plan E:

```text
D1 diagnostic baseline/oracle release
  -> E external research decision release
  -> D2 final specification + minimum observatory release
```

Plan D1 is the first implementation-ready planning unit under Program 1 —
**Truth Contract & Quality Observatory**. It establishes the reproducible
current-system diagnosis, frozen evaluation contract, and minimum observability
groundwork required before Program 2 changes the compiler or Program 3 changes
retrieval/serving.

It preserves the vault-as-codebase intent: an agent must be able to inspect,
retrieve, follow dependencies, verify exact evidence, and rerun quality checks
against a declared vault/corpus state. Plan D measures whether the current
system can do that. It does not prematurely redesign the compiler or serving
runtime.

## Strict Quality Condition

- No suspected failure may be declared fixed, accepted, or assigned without a
  reproducible evidence bundle.
- No production behavior may be changed before its current failure baseline is
  captured.
- A valid `source_span_id` is never treated as proof of claim support.
- Every metric is reported per query/task family and execution mode; aggregate
  only quality claims are prohibited.
- Deterministic provider-free gates, configured-provider benchmarks, degraded
  modes, and human semantic review remain separate.
- No release threshold is binding until its labeling procedure, baseline,
  variance, and user-approved threshold are documented.
- The observatory may implement only substrate required by a reproduced
  measurement blocker.

## Locked Design Decisions (Arena Consensus)

1. Every umbrella failure F1-F13 becomes a versioned failure-atlas record with
   one status: `reproduced`, `disproven`, `accepted`, or `assigned`.
2. Every reproduced failure has a minimal fixture, exact boundary diagnosis,
   commands/requests, oracle version, and captured before-state evidence.
3. Ground truth uses deterministic identities first, claim-to-minimal-support
   labels second, graded relevance/task labels next, and model judges only as
   supplementary diagnostics.
4. The evaluation corpus is partitioned into development, frozen regression,
   holdout, adversarial, and optional opt-in live-vault samples.
5. Cross-client parity compares normalized backend evidence for equivalent
   requests while preserving Obsidian's client-owned immediate viewer context.
6. Current stale EXH/qmd scenario assets are inventoried as historical evidence;
   current-architecture scenarios are authored separately.
7. Current behavior is captured before repair. In particular, search-hit
   provenance loss and disconnected query traces must be reproduced before any
   approved adapter/trace changes.
8. Diagnostic evidence defaults to synthetic/testbed sources. Private live-vault
   excerpts are not persisted without explicit approval.
9. Program 2 and Program 3 consume the approved Plan-D oracle and cannot
   silently redefine it.
10. D1 stops after the frozen diagnostic/oracle handoff. D2 resumes only after E
    merges, owns final specification synthesis and approved minimum observatory
    groundwork, and does not absorb compiler or serving implementation.

## Program And Plan Dependencies

### Upstream dependencies

- The umbrella Arena and
  `.agents/plans/03_rag_knowledge_quality_stabilization.md` remain the governing
  scope and ordering contract.
- Higher-priority active work must be concluded or explicitly overridden before
  implementation begins.
- Implementation starts from merged `master` on a fresh Program 1 branch, never
  from another feature/release branch.
- The active testbed scenario must be explicitly confirmed before execution;
  do not assume `testbed_template`.

### Downstream dependencies

- Program 2 - Evidence Compiler Integrity - is blocked until Plan D publishes
  compiler/reconciliation/support fixtures, baselines, and approved gates.
- Program 3 - Agentic Query Serving & Sensemaking - is blocked until Program 2
  is merged and Plan D publishes retrieval/query/client-parity fixtures,
  qrels, hard negatives, and transaction/locator requirements.
- `A_rag_retrieval_provenance.md` is a Program 3 serving plan. It consumes this
  batch's outputs and must not run before the trusted compiler release.

### Scope exclusions

- retrieval/RRF/reranker tuning;
- new graph/community/entity-resolution algorithms;
- formula recovery;
- unified context-service implementation;
- answer-link implementation;
- quota/provider UI;
- autonomous edits to `03_Notes/`, `04_Resources/`, or `06_Archives/`.

## Evidence Ledger

Items recorded before implementation to keep diagnosis, schema, docs, and
runtime reality aligned.

### Current Repository And Schema Reality

- Search is DB-native and materializes authoritative records into
  `search_documents`/`search_chunks`; `.curator/Collections/` is derived.
- `HybridEngine` hydrates `EngineHit.source_span_ids` from search-document
  provenance and can persist its own `QTR-`.
- `retrieval/evidence.py::_search_hits()` currently creates `EvidenceItem`
  without copying the hydrated source-span ids.
- `QueryOrchestrator.fetch_context()` and `.run()` create their own `QTR-`
  records; evidence construction may invoke a separately persisting engine
  search.
- `QueryOrchestrator` resolves `CurationPolicy`, but
  `build_evidence(paths, request, route)` does not receive the policy.
- global evidence loads all reports and source-section evidence loads all spans;
  `EvidencePack.evidence_block()` stops at 16,000 characters.
- current tests prove route and trace presence, but do not prove one logical
  transaction, claim-level support, policy enforcement across all routes,
  boundedness, or cross-client evidence parity.
- the `complex_math_backprop` scenario contains retired EXH/qmd-era behavior and
  is not a current architecture oracle.

### Current Dirty Worktree

- The worktree is shared and dirty with changes outside this batch's ownership.
- During this planning task, only
  `.agents/plans/current_system_failure_atlas_arena/**` and this file are owned.
- Before implementation, record `git status --short --branch`, current commit,
  active branch, and unrelated changes. Do not reset, revert, or overwrite them.

### Required Baseline Snapshot

Before any Program 1 code/spec/test change:

- current git SHA and branch;
- DB schema fingerprint and authoritative table counts;
- source/corpus hashes;
- current `curate.yml` and search-config hashes;
- search index/chunk/provider/model fingerprints;
- prompt/model identities for LLM-sensitive cases;
- active testbed scenario and exact initialization command;
- deterministic current baseline evidence for F1-F13.

### Rollback Requirements

- Create a DB backup and record its hash before any observatory migration or
  persistent trace/schema change.
- Record a clean rollback anchor at the Program 1 branch base.
- Prefer additive schema changes and rebuildable derived state.
- If observatory changes corrupt authoritative state, restore the DB backup and
  return to the last passing phase; do not attempt a corrective wrapper.
- If QA fails three consecutive times for the same root cause, activate
  `rollback_strategist`, restore the last stable phase commit, and return to the
  plan/specification decision.
- Testbed-specific config/path changes must be reverted before the phase ends.

## Required Deliverables

### D1 - Failure Atlas

For each F1-F13:

- stable case id and owner;
- status and impact;
- exact boundary;
- minimal fixture;
- commands/requests;
- before-state evidence;
- deterministic and semantic oracles;
- observed result;
- downstream assignment or accepted contract.

### D2 - Evaluation Specification

- query/task families;
- dataset partitions;
- qrels and graded relevance;
- claim-to-minimal-support labels;
- hard negatives and contradictions;
- locator and multi-hop/path expectations;
- human-review procedure;
- provider/latency/token environment;
- metrics, variance, and proposed gates.

### D3 - Experiment And Evidence-Bundle Contract

- run/case/oracle identities;
- corpus/config/model/schema identities;
- normalized requests and selected evidence;
- exact support/locator references;
- trace export and warnings;
- retention/privacy policy;
- comparison/report format.

### D4 - Minimum Observatory Specification

Only reproduced measurement blockers may justify:

- authoritative query-transaction identity or explicit parent/child trace model;
- corpus/config/model/search epoch identities;
- structured trace/evidence export;
- evaluation runner and holdout support;
- normalized cross-client inspection;
- critical provenance adapter repair required to make measurement truthful.

### D5 - Program Handoff Packages

- Program 2: compiler/mutation/support failures and gates.
- Program 3: retrieval/query/client/locator/budget/policy failures and gates.
- Explicit accepted limitations with owners and user-visible contracts.

## Execution Phases (Follow TDD And CI At Each Phase)

### P0 - Approval, Branch, And Evidence-Ledger Freeze

Actions:

- obtain user approval for this Master Plan;
- conclude or explicitly override higher-priority active work;
- create a fresh Program 1 branch from merged `master`;
- update relay/roadmap only under the Universal Strict Workflow;
- confirm the active testbed scenario;
- capture the required baseline snapshot and rollback anchor;
- author the separate coding-time evidence ledger required by repository rules.

Verify:

- no production behavior changed;
- worktree scope and unrelated changes recorded;
- DB backup and branch rollback anchor verified;
- active scenario and providers declared.

Stop condition:

- stop if the baseline cannot be reproduced or the active scenario is unknown.

### P1 - Failure Atlas And Oracle Specification

Actions:

- translate F1-F13 into complete case records;
- define behavioral oracles and labels before writing diagnostic runner code;
- define privacy/retention and artifact location;
- define status/assignment rules;
- update the relevant static specs and English/Korean guides for approved
  diagnostic contracts before implementation.

TDD:

- write schema/contract tests for atlas records and evidence bundles;
- write failing tests that reject missing snapshot identities, missing oracles,
  aggregate-only reports, or unsupported status transitions.

Verify:

- every F1-F13 has a case record;
- every record declares an oracle and expected evidence;
- docs/specs are synchronized;
- focused pytest and ruff pass.

### P2 - Minimal Deterministic Reproduction Fixtures

Actions:

- create minimal provider-free fixtures for provenance, policy, bounded routes,
  mutation/reconciliation, graph noise, authored topology, long-source recall,
  iterative gap, client parity, and current-architecture testbed behavior;
- reproduce F1 search-hit provenance loss and disconnected trace behavior before
  any fix;
- inventory stale scenario assumptions without modifying historical assets
  beyond the approved scope.

TDD:

- each fixture begins as a failing behavioral test or diagnostic assertion;
- tests distinguish identity validity, support correctness, support
  completeness, locator resolution, and freshness.

Verify:

- every deterministic suspected failure is reproduced or disproven;
- no production repair was made to obtain the result;
- focused pytest, ruff, and scenario scripts pass as diagnostics.

### P3 - Mutation, Degradation, And Cross-Client Experiments

Actions:

- run unchanged rebuild and edit/delete/rename/split/failed-batch experiments;
- test missing embedder/reranker/expander/LLM modes;
- compare raw search, fetch-context, query, CLI/plugin JSON, and Obsidian
  provider-context assembly for equivalent requests;
- capture per-case evidence bundles and baseline metrics.

Verify:

- every run declares corpus/config/model/schema identity;
- client parity comparison separates backend evidence from client-owned
  immediate context;
- testbed-specific configuration is restored;
- no live-vault/private source text is persisted without approval.

### P4 - Ground-Truth Labels, Holdout, And Baseline Report

Actions:

- label minimal claim support, graded relevance, routes, paths, locators, hard
  negatives, and contradictions;
- freeze regression and holdout partitions;
- measure baseline metrics and LLM-sensitive variance;
- propose evidence-backed thresholds for user approval.

Verify:

- labels have documented methods and reviewer provenance;
- no tuning was performed against holdout;
- reports are per family/mode and include latency/token/cost where available;
- model judges are not sole gates.

### Intermission Gate — Merge D1, Execute E, Resume As D2

After P0-P4:

- publish/classify the D1 Failure Atlas baseline, oracles, labels, holdout, and
  experiment/evidence-bundle contract;
- complete D1 review/CI/version/release/PR and merge it to `master`;
- execute and merge Plan E from the D1 baseline;
- start a fresh D2 Program-1 observatory branch from post-E `master`;
- refresh the evidence ledger and rollback anchor;
- synthesize the §6 final target specifications from D1 + E and obtain approval.

Stop if E is unmerged or the final target specifications are unapproved.

### P5 - Final Specification Synthesis And Minimum Observatory Groundwork

Prerequisite:

- merged D1 and E releases;
- user approval of D1-D4, Plan-E decisions, final target specifications, and
  explicit justification from reproduced measurement blockers.

Actions:

- implement only the approved trace/snapshot/export/evaluation substrate;
- if required for truthful measurement, repair only the critical provenance
  adapter that otherwise invalidates observatory results;
- keep derived state rebuildable and schema changes additive.

TDD:

- write failing tests for each approved observability contract first;
- include migration, backup/restore, trace identity, snapshot, and export tests.

Verify:

- the observatory records behavior without changing ranking/answers;
- one logical request is reconstructable under the approved transaction model;
- deterministic repeatability passes;
- rollback from migration/state changes is proven.

### P6 - Classification, Program-1 Handoff, And D2 Release Gate

Actions:

- classify every F1-F13;
- publish Program 2 and Program 3 handoff packages;
- publish final Program-2/3 handoffs incorporating D1, E, and D2;
- record accepted limitations and owners;
- complete sequential role review:
  `coder_engineer` -> `peer_reviewer` -> `schema_guardian` ->
  `source_pair_analyst` -> `qa_runner` -> `docs_sync_manager` ->
  `legacy_sweeper`;
- complete version/changelog/release workflow if code changed.

Verify:

- no unclassified concern remains;
- downstream plans cite the exact approved oracle/handoff version;
- Program 2 can begin only from merged D2 `master`;
- all docs/specs/guides and Korean counterparts are synchronized;
- full local CI and current testbed pass.

## Quality Gates

### Diagnostic completeness

- 100% of F1-F13 classified with evidence.
- 100% of reproduced defects have minimal fixtures and exact boundary
  diagnoses.
- 0 status transitions to accepted/assigned without owner, impact, and contract.
- 0 current-behavior repairs before before-state evidence capture.

### Truth and provenance

- 100% selected source-supported gold evidence resolves to authoritative records
  and source spans.
- Claim support correctness/completeness is measured separately from id validity.
- 0 fabricated working-looking links in diagnostic outputs.
- Every evidence bundle declares freshness/snapshot identity.

### Evaluation integrity

- Every query/task family has development, regression, and holdout coverage as
  applicable.
- No holdout tuning.
- No model-judge-only gate.
- Deterministic, full-provider, degraded, and semantic-review results are
  separate.

### Operational integrity

- DB backup/restore and derived-state rebuild are verified before release.
- Testbed paths/config are restored.
- Full local CI passes:

```bash
export UV_PROJECT_ENVIRONMENT="$(git rev-parse --show-toplevel)/.venv"
uv run --directory backend pytest -q
uv run --directory backend ruff check src/
uv run --directory backend mypy src/
npx vitest run -c ./plugin/vitest.config.ts
```

- Active testbed initialization and relevant current-architecture scenarios
  pass, or exact external dependency blockers are documented.

Plan D1 completion does **not** complete Program 1. Program 1 completes only
after Plan E merges and Plan D2's final target specifications plus approved
minimum observatory release merge to `master`.

## Documentation And Test Surfaces

Implementation must update all affected current contracts, English first and
then faithful Korean counterparts:

- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`
- `docs/specs/curator_schema/SCHEMA.md`
- `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`
- `docs/specs/plugin_schema/PLUGIN_SCHEMA.md` when client trace contracts change
- `docs/guides/USER_GUIDE.md`
- `docs/guides/WORKFLOW_GUIDE.md`
- `docs/guides/MCP_USER_GUIDE.md`
- `docs/guides/AGENT_WORKFLOW_GUIDE.md`
- `docs/guides/PLUGIN_GUIDE.md` when client inspection behavior changes

Required tests include focused backend pytest, plugin `.test.ts` where client
contracts are involved, current-architecture testbed diagnostics, mutation
scenarios, and full local CI.

## Stop Conditions

- Stop now: this is planning only and no implementation is authorized.
- Stop before P0 until user approval and a fresh branch from merged `master`.
- Stop if diagnosis requires changing production output before baseline capture.
- Stop if a metric lacks a labeling procedure or a report hides per-family
  regressions.
- Stop if observatory scope expands beyond a reproduced measurement blocker.
- Stop if Program 2 or Program 3 implementation is pulled into Plan D.
- After three repeated QA failures for the same blocker, activate
  `rollback_strategist`, restore the last stable phase, and return to planning.

---

## Plan E P7 Research Handoff (2026-06-12)

Source: `backend/research_spikes/reports/p7.md`, `backend/research_spikes/manifests/p7.yml`.
These are binding specification requirements handed off at Plan E P8. They do
not authorize implementation outside this plan's own phases and gates.

### Adopted Contract: Fine-Grained RAG Diagnostics (`adopt-contract`, confirmed at P7)

D2's evaluation and release gates MUST report, separately and per query
family (direct-factual, source-scoped, associative, global):

- Recall@k and MRR per family — never aggregated across families in a gate.
- Top-1 citation correctness and citation completeness against expected spans.
- Provenance resolution rate (every returned hit must resolve to source spans).
- Hard-negative outrank counts.
- Cost (indexed characters / latency) alongside quality, not in place of it.

Holdout proof (RUQ05): aggregate Recall@5 alone reported `1.00` on a blind
probe while top-1 citation correctness (`0.00`) and hard-negative outranks
(`2`) exposed the failure. Therefore the following are REJECTED DEFAULTS for
any D2 gate: aggregate-only retrieval reporting, and model-judge-only release
gates.

### Failure Atlas Holdout Reservation

The qrels holdout (`Q06`) was deliberately NOT consumed by Plan E P7. D2 must
define the approved single-run evaluation procedure that consumes it, with the
same no-tuning discipline Plan E applied to its own holdouts (frozen inputs,
single measurement, provenance audit, decision recorded before any re-run).

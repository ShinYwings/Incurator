# Program 3A Master Implementation Plan: Retrieval, Provenance, And Resolvable Source Locators

Date: 2026-06-11
Status: DRAFT - Arena debate concluded; planning only; implementation is blocked on merged Programs 1 and 2 plus user approval
Arena: `.agents/plans/rag_retrieval_provenance_arena/`
Umbrella: `.agents/plans/03_rag_knowledge_quality_stabilization.md`

## 0. Purpose And Program Position

Plan A delivers the trusted retrieval and evidence-selection substrate consumed
by the Program-3 ContextService. It selects bounded, query-relevant prior
knowledge, preserves exact provenance through every retrieval stage, records one
authoritative `RTR-*` retrieval execution under the caller-owned root QTR, and
produces resolvable structured source
locators.

This batch belongs mainly to Program 3 - **Agentic Query Serving &
Sensemaking**. It is intentionally not the first stabilization release:

```text
Program 1 truth/evaluation/observability merged
  -> Program 2 trusted evidence compiler merged
  -> Program 3 Plan A retrieval/provenance/locators
```

Serving must consume trusted Program 2 support and Program 1 quality gates. It
must not compensate for unstable identities, stale artifacts, or unsupported
claims with polished links or broader evidence.

## Strict Quality Condition

- No Plan A implementation begins before Program 1 and Program 2 release gates
  are merged on `master`.
- Every selected source-supported evidence item preserves trusted record
  identity, minimal support spans, freshness state, and a structured locator.
- Every retrieval route enforces KRS/scope/truth/freshness/candidate-budget/
  degradation rules.
- No rendered link may look actionable unless it resolves to the intended exact
  target or visibly degrades to a valid broader target with a warning.
- Direct factual retrieval is the protected baseline; graph/global/iterative
  retrieval cannot improve broad tasks by hiding prohibited factual regression.
- Retrieval changes are accepted only against frozen Program 1/2 regression,
  holdout and adversarial suites.
- The retrieval-result contract is transport-neutral and contains no MCP,
  plugin, Obsidian, progressive-pack, or feedback behavior owned by Plan F.

## Locked Design Decisions (Arena Consensus)

1. One retrieval coordinator owns route selection, candidate generation,
   evidence selection, provenance validation, and one authoritative retrieval
   execution (`RTR-*`) consumed by Plan F.
2. Raw search remains diagnostic; agent-facing transport and progressive context
   operations belong exclusively to Plan F.
3. A retrieval execution is a child action of the caller-owned Program-1 root
   `QTR-*`/snapshot contract. Standalone diagnostic retrieval creates an explicit
   diagnostic parent QTR through that substrate; it never creates a disconnected
   competing root. Plan F later owns the context-request root lifecycle.
4. Structured locators supplement, never replace, authoritative source-span ids.
5. Locator rendering happens at interface boundaries. `projection_path` remains
   a display locator only.
6. Block ids are file-scoped; duplicate/stale/unknown anchors never produce
    guessed links. Fallback targets are valid, broader, and warned.
7. Direct factual/local retrieval remains the protected baseline.
8. Context-enriched chunks, graph-guided expansion, PPR, selected-community
    global flows, corrective retrieval, and bounded iteration are candidates
    adopted only when targeted quality gates pass.
9. Retrieval results are not a new knowledge source of truth, public context
   pack, or frozen answer cache.
10. Plan F alone owns `ContextService`, public adapters, progressive packs,
    cross-client parity, optional synthesis, and feedback lineage.

## Program And Batch Dependencies

### Hard entry gates

Plan A implementation is blocked until all are true:

- Program 1 current-system Failure Atlas and evaluation specification are
  approved and merged.
- Program 1 observability/query-transaction substrate needed by serving is
  merged and passing, including complete root-QTR/snapshot creation usable by
  Plan-A diagnostic and compatibility callers.
- Program 2 compiler audit proves stable identities, minimal claim support,
  freshness/reconciliation, and source-locator contracts.
- Program 2 is merged to `master`; Plan A starts from that merged state on a
  fresh Program 3 branch.
- The trusted Program 2 corpus has a measured serving baseline on Program 1
  regression and holdout suites.
- Exact Program 3 schema/API/migration/rollback specs are approved before code.

### Upstream artifacts consumed

- `D_current_system_failure_atlas.md` outputs:
  failure classifications, qrels, holdouts, hard negatives, cross-client cases,
  query-transaction requirements, and baseline metrics.
- Program 2 outputs:
  trusted Knowledge IR, minimal support, truth/freshness state, stable record and
  dependency identities, structured source locators, compiler audit.
- Program-1 external research decisions from
  `E_external_research_design_matrix.md`.

### Downstream and adjacent dependencies

- `F_agent_context_service.md` consumes Plan A's retrieval-result, transaction,
  provenance, locator, and `RTR-*` contracts and owns the root `QTR-*` plus all
  public/client integration.
- Quota/storage UI and unrelated provider UI remain separate milestones.
- Compiler/entity/community fixes discovered during Plan A return to Program 2
  follow-up planning; they are not patched in serving.

### Scope exclusions

- compiler identity/support/reconciliation repair;
- formula recovery or extraction changes;
- entity merge/community compiler changes;
- web search as unlabeled vault evidence;
- autonomous edits to `03_Notes/`, `04_Resources/`, or `06_Archives/`;
- quota/provider UI;
- public ContextService operations, progressive context expansion, feedback,
  promotion, MCP/plugin migration, or cross-client UX;
- implementation during this planning task.

## Evidence Ledger

Items verified before implementation to prevent serving contracts from diverging
from current repository and trusted predecessor releases.

### Current Repository And Serving Reality

- `HybridEngine` already provides DB-native lexical/vector/RRF/rerank retrieval,
  hydrated `EngineHit.source_span_ids`, ranking contributions, explicit
  degradation warnings, and optional persisted `QTR-`.
- `retrieval/evidence.py::_search_hits()` currently drops hydrated
  `source_span_ids` when creating `EvidenceItem`.
- local evidence `source_span_ids` currently derives from entity evidence rather than
  all selected search evidence.
- `QueryOrchestrator` creates its own traces and does not incorporate the
  engine's full persisted retrieval transaction.
- `QueryOrchestrator` resolves `CurationPolicy`; `build_evidence()` does not
  receive it.
- global route loads synthesis plus every report; source-section loads every
  span; explore takes fixed report primers.
- `EvidencePack.evidence_block()` uses a fixed 16,000-character limit.
- current public consumers can drop or reshape retrieval detail; Plan F owns
  their final migration.
- plugin answer-link parsing currently recognizes PDF page/section patterns but
  does not define a complete file/heading/block/PDF/external structured locator.
- search spec states `projection_path` is a display locator only.

These are current observations only. Plan A's actual baseline must be recaptured
after Programs 1 and 2 merge because predecessor releases may intentionally
change them.

### Current Dirty Worktree

- The current worktree is shared and dirty outside this plan's ownership.
- During this planning task, only
  `.agents/plans/rag_retrieval_provenance_arena/**` and this file are owned.
- Before implementation, record branch/SHA/status and do not revert unrelated
  work.

### Required Program-3 Baseline Snapshot

Immediately before implementation:

- merged Program 1 and Program 2 release SHAs;
- trusted compiler audit version and pass report;
- DB schema and migration baseline;
- authoritative corpus, search index, KRS/policy, model/provider fingerprints;
- exact retrieval-result/query-transaction/locator contracts approved in specs;
- full-quality and degraded serving baseline;
- active testbed scenario and external Reference Mode locator fixtures;
- current raw-search/query evidence baseline.

### Rollback Requirements

- Create and hash a DB backup before serving schema migration.
- Record a clean Program 3 branch-base rollback anchor.
- Keep search/result caches derived and rebuildable.
- Introduce service operations and compatibility delegation incrementally.
- Do not remove old paths until parity and rollback tests pass.
- Rollback restores the DB backup and previous compatible backend/plugin pair;
  do not use destructive down-migrations or serving wrappers that conceal
  corrupted state.
- Revert testbed-only path/config changes before each phase ends.
- After three repeated QA failures for the same root cause, activate
  `rollback_strategist`, restore the last stable phase commit, and return to the
  plan/specification decision.

## Target Contracts

### Internal retrieval request

```json
{
  "query": "How is residual learning interpreted?",
  "workspace_path": "...",
  "purpose": "ground",
  "route": "auto",
  "scope": {"source_ids": [], "active_paths": []},
  "limits": {
    "max_candidates_per_stage": 100,
    "max_selected_items": 24,
    "max_graph_hops": 2,
    "max_iterations": 1
  },
  "freshness_policy": "current_only",
  "root_trace_id": "QTR-...",
  "snapshot_id": "SNAP-..."
}
```

Purposes: `ground | verify | synthesize | discover`.

### Internal retrieval result

```json
{
  "contract_version": "1",
  "root_trace_id": "QTR-...",
  "retrieval_execution_id": "RTR-...",
  "snapshot_id": "SNAP-...",
  "route": {"selected": "local", "reason": "..."},
  "policy": {"applied_filters": [], "excluded": []},
  "selection": {
    "candidate_count": 84,
    "selected_count": 18,
    "omitted_items": 7
  },
  "items": [],
  "warnings": []
}
```

This is an internal, transport-neutral result consumed by Plan F. The caller
creates the complete root QTR/snapshot through the Program-1 substrate; Plan A
executes strictly within those identities. Plan F later owns that lifecycle for
context requests. This result is not the public ContextService pack and does not
define expansion handles, client budgeting, or feedback.

### Evidence item

Each item includes:

- stable record id/kind/layer/hash;
- compact claim/summary;
- truth/authority and freshness;
- relevance/ranking contributions and selection reason;
- minimal supporting spans and immediate dependencies;
- structured locator and resolution state;
- snapshot identity;
- explicit provisional/stale/unsupported/degraded warnings.

### Structured locator

```json
{
  "source_id": 42,
  "source_kind": "vault_markdown",
  "relpath": "03_Notes/Residual Learning.md",
  "heading": "Optimization",
  "block_id": "residual-identity",
  "page_number": null,
  "toc_id": null,
  "external_uri": null,
  "locator_status": "exact"
}
```

Resolution states include at minimum:
`exact | fallback_file | fallback_source | duplicate_anchor | stale |
unavailable`.

## Execution Phases (Follow TDD And CI At Each Phase)

### P0 - Entry-Gate Audit, Approval, Branch, And Evidence Ledger

Actions:

- verify Programs 1 and 2 are merged and their required gates pass;
- recapture current serving reality against the merged trusted compiler;
- obtain approval of this Master Plan and exact Program 3 target
  schema/API/migration/rollback specs;
- create a fresh Program 3 branch from merged `master`;
- confirm active testbed and external Reference Mode locator fixtures;
- create DB backup, rollback anchor, and coding-time evidence ledger.

Verify:

- no Plan A code before all hard entry gates;
- predecessor evidence versions recorded;
- current baseline reports reproduced;
- unrelated worktree changes preserved.

Stop condition:

- stop if compiler audit, minimal support, stable identity, freshness, or locator
  gates fail; return the issue to Program 2 planning.

### P1 - Specs, Retrieval Contract, And Contract Tests

Actions:

- update static specs for retrieval transaction, route, candidate, ranking,
  selection, provenance, and locator contracts;
- define the internal retrieval-result boundary consumed by Plan F;
- define schema migration and compact retrieval-transaction retention;
- update English guides first, then Korean counterparts.

TDD:

- write failing backend retrieval contract tests;
- write migration/rollback tests;
- write tests rejecting unsupported evidence upgrades, policy bypass,
  unbounded routes, and fabricated locators.

Verify:

- every retrieval surface and Plan-F handoff has an explicit contract;
- specs/guides are synchronized;
- focused pytest, plugin tests, and ruff pass.

### P2 - One Authoritative Retrieval Execution And Evidence Selection Core

Actions:

- implement authoritative `RTR-*` retrieval execution orchestration attached to
  a caller-owned root QTR and snapshot;
- attach route, candidate generation, ranking, evidence selection, provenance
  validation, degradation, and stop actions;
- eliminate disconnected engine/orchestrator retrieval roots;
- emit the internal retrieval-result contract consumed by Plan F.

TDD:

- one logical context request creates one root QTR and one reconstructable
  retrieval child execution;
- identical requests under unchanged state produce equivalent selected evidence;
- no retrieval operation silently changes knowledge truth.

Verify:

- Program 1 transaction/reproducibility gates pass;
- retrieval execution and result contracts pass;
- DB backup/restore and migration rollback are proven.

### P3 - Policy, Freshness, And Bounded Route Selection

Actions:

- enforce KRS/source scope/truth/freshness on every retrieval route;
- implement route/candidate/evidence limits and explicit selection omissions;
- bound global, source-section, and explore routes.

TDD:

- excluded sources never enter selected evidence;
- stale/provisional evidence obeys freshness policy;
- every route stays within candidate/evidence limits and reports omissions;

Verify:

- policy, boundedness, freshness, and degradation suites pass;
- direct factual baseline is unchanged before retrieval enhancements.

### P4 - Provenance Preservation And Locator Resolution

Actions:

- preserve Program 2 minimal support through search hit -> evidence item ->
  retrieval result -> locator handoff;
- expose exact support/derivation/contradiction data for Plan F verification;
- resolve structured locator targets for Markdown file/heading/block, PDF
  physical/verified printed page/section, promoted Wiki, and external Reference
  Mode sources without rendering client UI;
- implement exact/fallback/stale/duplicate/unavailable states and warnings;
- validate links against real testbed targets.

TDD:

- selected search-hit provenance survives end to end;
- claim/evidence associations reference selected trusted evidence items;
- block ids resolve within the declared file;
- duplicate/stale anchors do not produce guessed links;
- exact target or valid warned fallback is guaranteed;
- no user note is edited to add anchors.

Verify:

- 100% gold source-supported evidence is verifiable and locator-resolvable or
  explicitly unavailable;
- 0 fabricated working-looking links;
- backend locator-resolution fixtures cover note, heading, block, PDF
  page/section, and external references; Plan F owns plugin navigation tests.

### P5 - Plan-F Handoff And Locator Compatibility Validation

Actions:

- publish the stable internal retrieval-result and locator-resolution contracts;
- validate that existing diagnostic/query surfaces can consume the result without
  dropping provenance while Plan F migration remains pending;
- provide Plan F fixtures for local/global/explore/source routes, degradation,
  policy, evidence selection, and locator states.

TDD:

- Plan F fixtures preserve selected evidence, ranking contributions, transaction,
  policy, warning, and locator fields;
- no compatibility surface fabricates support or locators.

Verify:

- Plan-F handoff contract passes;
- existing diagnostic behavior remains intact until Plan F replaces adapters.

### P6 - Measured Retrieval Improvements

Prerequisite:

- P2-P5 contracts and factual baseline pass on frozen Program 1/2 suites.

Actions:

- benchmark contextualized chunks, graph-guided organization, passage/entity
  PPR, selected-community global flows, corrective retrieval, and bounded
  iteration against reproduced target failures;
- adopt only winning candidates;
- tune routes/weights/models only against development data;
- preserve holdout and adversarial evaluation.

TDD:

- add candidate-specific failing tests only for reproduced target failures;
- assert bounded stop rules and selection explanations;
- assert direct factual protected-baseline tolerances.

Verify:

- targeted families improve by approved minimum;
- no prohibited factual, citation, policy, budget, latency, or degraded-mode
  regression;
- no graph-only or unbounded route.

### P7 - Sequential Review, Full QA, Release, And Handoff

Actions:

- run roles sequentially:
  `coder_engineer` -> `peer_reviewer` -> `schema_guardian` ->
  `source_pair_analyst` -> `qa_runner` -> `docs_sync_manager` ->
  `legacy_sweeper`;
- remove only compatibility paths whose explicit gates pass;
- complete docs/spec/guides synchronization;
- complete mandatory version/changelog/release commit/push/PR workflow.

Verify:

- all Plan A quality gates pass;
- full local CI and active testbed pass;
- rollback and mixed-version behavior are documented and tested;
- no retired qmd/EXH assumptions or unsupported compatibility semantics remain.

## Quality Gates

### Entry and trust

- Program 1 and Program 2 required releases merged.
- Program 2 compiler audit passes stable identity, minimal support, freshness,
  reconciliation, and locator gates.
- Serving baseline recorded on the trusted compiler corpus.

### Retrieval execution and provenance

- exactly one `RTR-*` retrieval execution attached to the caller-owned root QTR;
- 100% selected source-supported gold evidence preserves trusted record and
  minimal source-span identities;
- every material gold answer claim maps to selected retrieval evidence;
- no serving path broadens support to hide compiler gaps;
- deterministic repeatability under unchanged corpus/config/model/snapshot.

### Policy, bounds, and snapshots

- every route enforces KRS/source scope/truth/freshness under the caller-owned
  snapshot;
- every route stays within declared candidate/evidence limits;
- omissions and degradation are explicit;
- no retrieval execution runs under a different snapshot than its caller;
- global/source/explore routes are bounded and query-relevant.

### Links and verification

- 100% gold locators resolve exactly or return explicit valid fallback/
  unavailable state;
- 0 fabricated working-looking links;
- duplicate/stale block/heading anchors produce warnings, not guesses;
- Markdown file/heading/block, PDF page/section, promoted Wiki, and external
  Reference Mode fixtures pass.

### Retrieval and answer quality

- no query-family Recall@5 or nDCG@10 regression above approved tolerance;
- targeted failing families improve by approved minimum;
- direct factual quality remains within protected tolerance;
- citation correctness/completeness meet approved Program 1 thresholds;
- unsupported-answer, contradiction, and hard-negative rates do not regress;
- p50/p95 latency, tokens, and cost remain within approved route budgets.

### Plan-F handoff

- Plan F can consume the retrieval result without a second retrieval root;
- all selected evidence, ranking, policy, warnings, and locators survive the
  internal boundary;
- no public/client behavior is implemented under Plan A.

### Operational integrity

- DB migration backup/restore and compatibility rollback pass.
- Testbed-specific paths/config are restored.
- Full local CI passes:

```bash
export UV_PROJECT_ENVIRONMENT="$(git rev-parse --show-toplevel)/.venv"
uv run --directory backend pytest -q
uv run --directory backend ruff check src/
uv run --directory backend mypy src/
npx vitest run -c ./plugin/vitest.config.ts
```

- Active testbed passes full-quality and explicit degraded-mode serving cases,
  including external Reference Mode locator validation.

## Documentation And Test Surfaces

Implementation must update all affected source-of-truth contracts, English first
and then faithful Korean counterparts:

- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`
- `docs/specs/curator_schema/SCHEMA.md`
- `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`
- `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`
- `docs/guides/USER_GUIDE.md`
- `docs/guides/WORKFLOW_GUIDE.md`
- `docs/guides/MCP_USER_GUIDE.md`
- `docs/guides/AGENT_WORKFLOW_GUIDE.md`
- `docs/guides/PLUGIN_GUIDE.md`

Required tests include backend pytest for retrieval transaction, policy,
provenance, routing, ranking, boundedness, locator resolution, Plan-F handoff,
migration/rollback, frozen Program 1/2 evaluation suites, active testbed smoke,
and full local CI. Public ContextService and plugin tests belong to Plan F.

## Stop Conditions

- Stop now: this is planning only and no implementation is authorized.
- Stop before P0 if Program 1 or Program 2 is unmerged or any required trust gate
  fails.
- Stop and return issues to Program 2 if serving would need to invent stable
  identities, minimal support, freshness, or locators.
- Stop retrieval adoption if it lacks a reproduced target failure and measured
  comparison.
- Stop graph/global/iterative retrieval if it sacrifices factual quality beyond
  tolerance or violates boundedness.
- Stop link rendering if exact/fallback/unavailable states cannot be proven.
- Stop Plan-F handoff if it requires a second retrieval implementation or drops
  provenance.
- After three repeated QA failures for the same blocker, activate
  `rollback_strategist`, restore the last stable phase, and return to planning.

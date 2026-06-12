# Program 3F Unified Agent ContextService Master Implementation Plan

Date: 2026-06-11
Status: DRAFT — Arena debate concluded; blocked on merged Programs 1 and 2, merged Plan A retrieval substrate, target specs, and user approval

Arena:
`.agents/plans/agent_context_service_arena/`

Umbrella dependency:
`.agents/plans/03_rag_knowledge_quality_stabilization.md`

Research dependency:
`.agents/plans/E_external_research_design_matrix.md`

## 0. Purpose

Implement one backend `ContextService` that gives external agents and the
Obsidian agent equivalent normalized, source-grounded evidence packs under
explicit budgets and reproducible snapshots.

The service becomes the single context-serving transaction boundary for:

- context manifests;
- initial evidence fetch;
- progressive expansion;
- exact evidence/lineage verification;
- feedback and promotion lineage;
- optional backend answer synthesis over the exact same pack.

This is a Program-3 plan. It must not implement or compensate for untrusted
Program-2 compiler behavior. Stable identities, minimal support, structured
locators, and freshness/invalidation must exist before implementation starts.

## Strict Quality Condition

- Exactly one authoritative root `QTR-*` owns each context request and its
  ordered child actions; no disconnected retrieval/orchestration traces.
- 100% of selected source-supported evidence items have resolvable record ids,
  minimal supporting source span ids, structured locators, and freshness state.
- Every route applies the same workspace/KRS policy, scope, authority, freshness,
  snapshot, and budget enforcement.
- External MCP and Obsidian clients receive semantically equivalent normalized
  packs for equivalent request/snapshot inputs.
- All packs are budget bounded. Truncation is never silent; omissions and
  expansion reasons are explicit.
- Expansion never silently mixes snapshots. Snapshot conflict/rebase behavior is
  typed and tested.
- Backend synthesis is optional and consumes the exact pack without launching a
  divergent retrieval path.
- Feedback is append-only, lineage-complete, source-truth-safe, and quarantined
  from ranking/truth effects until reviewed and measured.
- Direct factual retrieval and citation quality cannot regress beyond thresholds
  approved from Program-1/2 evaluation.

## Locked Design Decisions (Arena Consensus)

### Service Boundary

1. One application façade named `ContextService` owns the normalized context
   contract.
2. The façade delegates to explicit internal ports:
   - snapshot resolver;
   - policy evaluator;
   - Plan-A retrieval execution port;
   - pack assembler and token budgeter;
   - provenance/locator validator;
   - trace recorder;
   - verification reader;
   - feedback recorder.
3. Existing public surfaces remain only as transport/compatibility adapters and
   must fully delegate to the service.

### Operations

- `context_manifest`
- `context_fetch`
- `context_expand`
- `context_verify`
- `context_feedback`

`curator_fetch_context` delegates to `context_fetch`.
`curator_query` delegates to `context_fetch`, then optionally synthesizes over
the exact returned pack using the same root transaction.
Raw search remains diagnostic; when used as agent context it must share policy,
snapshot, trace, and provenance primitives.

### Transaction And Snapshot

1. One root `QTR-*` represents the logical request.
2. Plan A attaches exactly one `RTR-*` retrieval execution to the caller-owned
   root QTR and complete snapshot. Ordered child actions preserve retrieval,
   expansion, verification, synthesis, degradation, and stop detail without
   creating disconnected root traces.
3. Snapshot closure includes source/corpus identity, DB epoch, search/index
   epoch, KRS/policy hash, relevant dependency/derived-state identity, and
   model/tokenizer/config identity used for retrieval and packing.
4. Expansion requires `pack_id`, handles, a new pack budget, and
   `expected_snapshot_id`.
5. Changed state returns a typed conflict. Clients explicitly refetch/rebase;
   the backend never silently mixes epochs.

### Pack And Budget

1. Progressive levels are `manifest`, `index`, `excerpt`, and `source`.
2. Pack budgets cover backend evidence only. Each client separately calculates
   its remaining provider context after system prompt, chat history, selected/
   pinned/local context, images, and tool overhead.
3. Use the model tokenizer where available; otherwise use a conservative
   estimator and expose estimation mode.
4. Enforce total tokens, item count, per-item tokens, route caps, and reserved
   expansion budget.
5. Included claims keep their minimal support and valid locator/provenance.
6. Omitted items, categories, coverage/insufficiency warnings, contradiction
   indicators, and prioritized expansion handles are explicit.

### Client Parity

1. Parity means equivalent normalized backend pack for equivalent request and
   snapshot, not identical final prompts.
2. Obsidian selected/open-note/PDF/image context remains client-local and
   highest priority.
3. The plugin requests a bounded backend pack using its remaining budget and
   grounds the provider with evidence items, not a synthesized backend answer by
   default.
4. Sources & Trace renders the exact pack used for reasoning.

### Feedback Lineage

1. Feedback types: relevant, irrelevant, incorrect, stale, insufficient,
   duplicate, new insight, correction, promotion request.
2. Every event retains root trace, pack, snapshot, client/purpose, target item/
   claim/record, reviewed evidence/source ids, classification, review status,
   and resulting artifact lineage.
3. Feedback is append-only and cannot mutate source truth silently.
4. Feedback cannot influence ranking/truth until a separately specified,
   reviewed, measured policy authorizes that effect.

## Scope And Non-Goals

### In Scope

- Backend ContextService contract and internal ports.
- Root/child transaction and snapshot contracts.
- Versioned evidence-pack, item, budget, omission, expansion, verification, and
  feedback contracts.
- MCP, CLI/plugin JSON, backend synthesis, and Obsidian adapter migration.
- Model-aware/conservative pack token accounting.
- Progressive disclosure and typed snapshot conflicts.
- Sources & Trace exact-pack rendering and navigation.
- Cross-client normalized-pack parity tests.
- Feedback lineage and explicit promotion handoff.
- Route-specific bounded serving using techniques approved by Program-1 research.

### Out Of Scope

- Compiler stable identity, reconciliation, formula recovery, entity resolution,
  graph denoising, hierarchy creation, or source-span repair owned by Program 2.
- Autonomous source/reference edits.
- Web retrieval labeled as vault truth.
- Unbounded retrieval/agent loops.
- Quota UI or unrelated provider settings.
- Compatibility paths that preserve a second retrieval implementation.

## Dependencies And Entry Gates

### Hard Program Dependencies

Program 1 must have merged:

- one authoritative truth/quality observatory contract;
- frozen evaluation families, labels, metrics, and holdouts;
- valid query/provenance trace substrate;
- approved external-design decisions relevant to Program 3.

Program 2 must have merged:

- stable record/semantic identities;
- exact minimal supporting evidence;
- structured note/heading/block/PDF/external locators;
- reliable authority/truth/freshness states;
- deterministic source/derived invalidation;
- trusted graph/hierarchy inputs for any graph/global routes.

Program 3 Plan A must be merged to `master` with:

- one authoritative `RTR-*` retrieval execution attached to a caller-owned root
  QTR and a transport-neutral retrieval-result contract;
- policy-aware bounded route/candidate/evidence selection exposed through the
  Plan-A retrieval port;
- complete source-span provenance and structured locator resolution;
- frozen retrieval and locator handoff fixtures consumed by this plan.

### Docs-First Entry Gate

Before implementation, update and approve the target contract in:

- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`
- `docs/specs/curator_schema/SCHEMA.md`
- `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`
- applicable search/query contract specs

Update English guides first, then faithful `_KR.md` counterparts:

- `USER_GUIDE`
- `WORKFLOW_GUIDE`
- `MCP_USER_GUIDE`
- `AGENT_WORKFLOW_GUIDE`
- `PLUGIN_GUIDE`

The physical DB migration, retention policy, compatibility/removal schedule, and
exact API names are frozen in those approved specs before code.

### Research Entry Gate

Only serving techniques approved as `adopt-contract` or explicitly authorized
`benchmark-later` experiments by Program-1 research may enter implementation.
Graph, adaptive, corrective, and iterative behavior must be route-gated and
measured separately.

## Evidence Ledger

This ledger must be refreshed immediately before coding begins.

### Current Repository And Schema Reality

Verified current surfaces to re-check:

- `backend/src/curator/retrieval/engine.py`: hybrid retrieval and its own durable
  trace behavior.
- `backend/src/curator/retrieval/evidence.py`: route-specific pack assembly and
  current provenance-loss boundary.
- `backend/src/curator/retrieval/orchestrator.py`: route/query synthesis and
  second trace behavior.
- `backend/src/curator/retrieval/models.py`: current `EvidenceItem`,
  `EvidencePack`, `QueryRequest`, and result contracts.
- `backend/src/curator/db.py`: `query_traces`, prompt runs, evidence/source ids,
  insight candidates, and artifact dependencies.
- `backend/src/curator/mcp_server.py`: `curator_query`,
  `curator_fetch_context`, search, feedback, and promotion surfaces.
- `backend/src/curator/cli.py` and `backend/src/curator/plugin_api.py`: plugin
  command and trace boundaries.
- `plugin/src/agent/incuratorClient.ts`: backend/plugin client normalization.
- `plugin/src/ui/chatSidebar.ts`: current provider-context assembly and backend
  query injection.
- `plugin/src/context/providerContextPolicy.ts` and
  `plugin/src/context/chatContextPriority.ts`: local/selected context priority.
- `plugin/src/ui/incuratorQueryTrace.ts`: Sources & Trace rendering.

Verified starting defects to reproduce:

- search-hit `source_span_ids` dropped in evidence assembly;
- disconnected hybrid/orchestrator root traces;
- incomplete KRS enforcement;
- unbounded/query-independent global and source routes;
- fixed 16,000-character evidence cutoff;
- divergent external and Obsidian context behavior.

### Current Dirty Worktree

- Record exact `git status --short --branch` at execution start.
- Work from a new Program-3 branch created from merged `master`.
- Do not revert, stage, or include unrelated user/agent changes.
- Update `RELAY.md` only when the approved workflow begins; this planning task
  does not modify it.

### Active Testbed And External References

- Confirm the user-selected active scenario under `tests/scenarios/`; do not
  assume `testbed_template`.
- Preserve and explicitly validate external Reference Mode source locators and
  freshness without hard-copying sources into the vault.
- Record testbed DB/source/search/policy epochs and hashes.

### Rollback Requirements

- Create DB backup and schema/migration rollback anchor before physical changes.
- Prefer additive schema migration and dual-read verification only when the
  approved migration spec requires it; do not retain permanent divergent paths.
- Keep old public adapters delegating to the service until parity tests and
  deprecation gates pass.
- Roll back Plan-A route admissions independently behind feature/experiment
  gates.
- If root-transaction, snapshot, provenance, or budget invariants fail, disable
  the new service path and restore the last stable adapter behavior through the
  approved rollback migration. Never hide failure with a fallback that produces
  untraceable evidence.
- After three repeated QA failures, activate `rollback_strategist`, restore the
  last stable branch/release state, and return to planning.

## Target Logical Contracts

Exact physical schema and field naming are finalized in static specs before
implementation. The following logical fields are locked.

### Context Request

```json
{
  "contract_version": "1",
  "query": "How is residual learning interpreted?",
  "workspace_path": "...",
  "purpose": "ground",
  "route": "auto",
  "scope": {
    "source_ids": [],
    "active_paths": []
  },
  "budget": {
    "max_tokens": 6000,
    "max_items": 12,
    "max_tokens_per_item": 700,
    "reserve_for_expansion": 1500
  },
  "detail": "index",
  "freshness_policy": "current_only",
  "expected_snapshot_id": null
}
```

Purposes: `ground | verify | synthesize | discover`.

### Context Pack

```json
{
  "contract_version": "1",
  "pack_id": "PACK-...",
  "trace_id": "QTR-...",
  "snapshot": {
    "snapshot_id": "SNAP-...",
    "source_epoch": "...",
    "db_epoch": "...",
    "search_epoch": "...",
    "dependency_epoch": "...",
    "policy_hash": "...",
    "model_config_hash": "...",
    "tokenizer_id": "...",
    "created_at": "..."
  },
  "route": {
    "selected": "local",
    "reason": "...",
    "stop_reason": "sufficient"
  },
  "policy": {
    "applied_filters": [],
    "excluded": []
  },
  "budget": {
    "limit_tokens": 6000,
    "used_tokens": 4310,
    "reserved_tokens": 1500,
    "omitted_items": 7,
    "estimation_mode": "tokenizer"
  },
  "coverage": {
    "sufficiency": "sufficient",
    "contradictions_present": false,
    "omission_categories": []
  },
  "items": [],
  "next": [],
  "warnings": []
}
```

### Evidence Item

Required logical fields:

- stable record id, record hash, kind, and L1-L4 layer;
- compact claim/summary distinct from raw source;
- authority/truth/freshness state;
- ranking contributions and route/expansion reason;
- structured note/heading/block/PDF/external locator;
- minimal supporting source spans and immediate dependencies;
- token cost and detail level;
- contradiction/uncertainty state;
- expansion and verification handles.

### Root Transaction And Child Actions

Root QTR records request identity, snapshot, policy, route decision, final pack,
warnings, and optional synthesis result references.

Ordered child actions record:

- retrieval stage and candidate ids/scores;
- expansion/traversal stage and added/removed evidence;
- pack/budget decisions and omissions;
- provenance/locator validation;
- degraded behavior and stop reason;
- synthesis prompt/run references;
- later expansion/verification actions linked to the root.

### Feedback Event

Required logical fields:

- feedback event id/type/status;
- root trace, pack, snapshot, client, and purpose;
- target item/record/claim;
- reviewed evidence/source span ids;
- user statement and classification;
- review actor/time;
- resulting insight/promotion/correction lineage;
- no implicit truth/ranking mutation.

## Execution Phases (Follow TDD And CI At Each Phase)

Each phase must pass focused tests, backend `pytest`, and `ruff` before the next
phase. Run `mypy` and plugin Vitest whenever affected, and full local CI at each
release gate.

### P0 — Dependency Audit, Baseline, And Evidence Ledger

Actions:

- confirm Programs 1 and 2 plus Plan A are merged and their gates passed;
- create a fresh Plan-F branch from post-A `master`;
- refresh repository/schema/client reality and active testbed;
- reproduce all six starting service failures;
- freeze baseline normalized outputs and per-family quality/latency/token metrics;
- record rollback anchors and migration constraints.

TDD:

- minimal reproductions for dropped search provenance, duplicate root traces,
  policy bypass, unbounded routes, fixed cutoff, and client divergence.

Verify:

- every defect has a failing test and pipeline-boundary diagnosis;
- no implementation starts if Program-2 minimal support/identity/freshness is
  absent.

Quality gate:

- stop and return the dependency to Program 1 or 2 rather than compensating in
  ContextService.

### P1 — Specs, Guides, Contract Fixtures, And Migration Plan

Actions:

- update static specs synchronously;
- update English guides, then Korean counterparts;
- finalize request/pack/item/snapshot/action/feedback schemas;
- finalize physical DB migration, retention, sync, and deprecation plan;
- create canonical JSON fixtures for each operation and degraded/conflict case;
- obtain user approval before application code.

TDD:

- schema/contract validation tests;
- serialization round-trip tests;
- compatibility fixture tests;
- migration forward/rollback tests designed before migration implementation.

Verify:

- all public/physical contracts, retention decisions, and removal gates are
  explicit;
- no old semantic behavior is preserved accidentally.

### P2 — Root Transaction, Snapshot Resolver, And Policy Port

Actions:

- implement one root context transaction and ordered child-action recording;
- implement snapshot closure and typed conflict/rebase response;
- make KRS/scope/authority/freshness policy a required shared port and pass the
  resolved decision plus complete snapshot into Plan A;
- ensure Plan A attaches one `RTR-*` to the caller-owned root trace instead of
  creating a disconnected root.

TDD:

- exactly-one-root trace tests;
- ordered child-action tests;
- deterministic repeatability under unchanged snapshot;
- source/DB/search/dependency/policy/model epoch conflict tests;
- KRS include/exclude and source-scope tests on every route.

Verify:

- one request produces one root and complete child lineage;
- snapshot conflicts are explicit;
- no route can bypass policy resolution.

Rollback gate:

- if trace/snapshot migration cannot preserve existing trace inspection, stop and
  revise the migration plan.

### P3 — Pack Assembler, Provenance Validator, And Token Budgeter

Actions:

- implement versioned evidence item and pack assembly;
- preserve search-hit and generated-record source evidence;
- enforce minimal support, locator validity, authority/truth/freshness rules;
- implement tokenizer-backed and conservative fallback accounting;
- enforce total/item/per-item/route/reserved-expansion budgets;
- emit omission categories, coverage, warnings, and prioritized handles.

TDD:

- search provenance preservation;
- invalid/missing support rejection or explicit provisional handling;
- exact locator validation;
- deterministic packing;
- token budget and estimator tests;
- no-silent-truncation tests;
- formula/code/citation boundary-preservation fixtures;
- bounded global/source route tests.

Verify:

- 100% selected supported items resolve to exact evidence;
- every omitted/truncated decision is explicit;
- pack stays within approved budgets.

### P4 — Progressive Operations And Verification

Actions:

- implement `context_manifest`, `context_fetch`, `context_expand`, and
  `context_verify`;
- implement manifest → index → excerpt → source expansion;
- bind expansion handles to pack/root/snapshot and enforce new budgets;
- expose exact claim/source/dependency/contradiction verification.

TDD:

- operation contract fixtures;
- expansion handle ownership and expiry/invalidity tests;
- same-snapshot expansion tests;
- typed conflict and explicit refetch/rebase tests;
- verification lineage completeness;
- external Reference Mode locator/freshness tests.

Verify:

- expansion never mixes snapshots;
- verification reaches minimal raw evidence and immediate dependencies;
- manifest and source expansions remain bounded.

### P5 — Unified Public Adapters And Optional Synthesis

Actions:

- make MCP context operations delegate to `ContextService`;
- migrate `curator_fetch_context` to the normalized pack;
- make `curator_query` synthesize only over the exact pack and same root trace;
- migrate CLI/plugin JSON adapter;
- keep raw search diagnostic behavior clearly separated while sharing required
  policy/provenance primitives;
- define and test deprecation/removal behavior for obsolete shapes.

TDD:

- adapter delegation tests;
- MCP/CLI normalized shape equivalence;
- synthesis-pack identity tests;
- no-second-retrieval/no-second-root tests;
- backward-compatibility/deprecation fixture tests;
- degraded-provider behavior and warnings.

Verify:

- all public context/query surfaces share one service;
- compatibility layers contain no retrieval logic;
- synthesized answers cite only the exact pack.

### P6 — Obsidian Agent Grounding And Sources & Trace

Actions:

- extend `incuratorClient` normalization for packs/snapshots/actions;
- update provider context assembly to calculate remaining client budget after
  system/history/selected/pinned/local/PDF/image context;
- request backend pack within that remaining budget;
- ground the provider with evidence items instead of backend synthesized answer
  by default;
- preserve selected/open-note/PDF/image priority;
- render exact pack route, evidence, budget, omissions, snapshot/freshness,
  degradation, expansion, verification, and working locators in Sources & Trace.

TDD:

- external/Obsidian normalized-pack parity;
- selected-context priority and no-backend fast-path regressions;
- remaining-budget calculation;
- exact-pack provider grounding;
- Sources & Trace rendering/navigation;
- snapshot conflict/refetch UX;
- registered/unregistered PDF and external Reference Mode cases;
- no default synthesized-answer injection.

Verify:

- equivalent backend requests return equivalent normalized packs;
- client-local context remains correctly prioritized;
- the UI shows the actual evidence used.

### P7 — Feedback And Promotion Lineage

Actions:

- implement append-only `context_feedback`;
- support all locked feedback types;
- attach root trace, pack, snapshot, target, reviewed evidence, and client/purpose;
- integrate with existing classification, insight candidate, review, and explicit
  `02_Wiki/` promotion lifecycle;
- quarantine feedback from ranking/truth effects.

TDD:

- lineage completeness for every feedback type;
- stale/incorrect/insufficient/duplicate cases;
- correction and promotion review gates;
- source/reference immutability;
- no implicit ranking/truth mutation;
- retention/sync/privacy contract tests.

Verify:

- every resulting candidate/promotion can trace to reviewed evidence and origin;
- feedback cannot edit source truth or alter serving silently.

### P8 — Plan-A Route Admission And Context-Service Integration

Actions:

- integrate only Plan-A retrieval routes that passed Plan-A quality gates;
- map Plan-A `RTR-*` results into progressive packs without rerunning retrieval;
- apply ContextService pack budgets, expansion, and client policies around the
  selected evidence;
- keep route enablement and rollback decisions synchronized with Plan A.

TDD:

- Plan-A handoff fixtures for every admitted route;
- no-second-retrieval and no-second-root assertions;
- route result to pack accounting/provenance preservation;
- route disable/rollback propagation.

Verify:

- every admitted route retains its approved Plan-A evidence and `RTR-*` detail;
- no ContextService layer duplicates route planning/ranking/execution;
- all admitted routes emit complete pack accounting.

Rollback gate:

- disable any enhancement independently when it fails quality, cost, latency,
  provenance, or factual non-regression gates.

### P9 — Cross-Client E2E, Testbed, Migration, And Release

Actions:

- execute end-to-end external MCP and Obsidian agent tasks;
- run edit/delete/freshness/snapshot-conflict and Reference Mode scenarios;
- run full migration forward/rollback rehearsal on copied DB;
- perform execution-role reviews;
- complete docs synchronization and legacy sweep;
- run full local CI and active testbed;
- perform mandatory version/changelog/release workflow.

Sequential roles:

```text
coder_engineer
  -> peer_reviewer
  -> schema_guardian
  -> source_pair_analyst
  -> qa_runner
  -> docs_sync_manager
  -> legacy_sweeper
```

Local CI:

```bash
export UV_PROJECT_ENVIRONMENT="$(git rev-parse --show-toplevel)/.venv"
uv run --directory backend pytest -q
uv run --directory backend ruff check src/
uv run --directory backend mypy src/
npx vitest run -c ./plugin/vitest.config.ts
```

Testbed:

- initialize only from the confirmed active scenario when needed;
- validate status/add/sync/lint/update and query/context operations;
- validate external Reference Mode sources without hard copying;
- run LLM-sensitive checks when the configured provider is available;
- restore any temporary test configuration before completion.

Release:

- remove completed plan files only at the Universal Strict Workflow step;
- bump `pyproject.toml`, `package.json`, and `manifest.json` to the same version;
- update `CHANGELOG.md`;
- create final `chore(release): vX.Y.Z`;
- push and open PR only after all gates pass.

## Required Test Matrix

### Backend Unit And Integration

- request normalization and purpose/route/scope validation;
- snapshot closure, identity, conflict, and explicit rebase/refetch;
- one root trace and ordered child actions;
- KRS/scope/authority/freshness enforcement on every route;
- provenance and locator validation;
- deterministic budget packing and omission reasons;
- progressive expansion and exact verification;
- optional synthesis over exact pack;
- feedback lineage and source-truth immutability;
- adapter delegation and compatibility removal.

### Plugin Tests

- normalized pack parsing;
- remaining provider budget calculation;
- selected/pinned/local/PDF/image priority;
- evidence-pack grounding;
- no default backend-answer injection;
- Sources & Trace exact-pack rendering;
- working note/heading/block/PDF/external locators;
- omissions, degradation, and snapshot conflict UX;
- feedback/promotion lineage calls.

### E2E Families

- direct factual;
- source-scoped factual;
- associative/multi-hop;
- broad/global;
- contradiction/verification;
- agentic progressive retrieval;
- changed/deleted/stale source;
- Korean query;
- missing vector/reranker/LLM provider;
- external Reference Mode source;
- MCP/Obsidian parity.

## Release Quality Gates

- Exactly one root QTR for every context/query request.
- 100% selected supported evidence has valid record, minimal source evidence, and
  structured locator identity.
- 0 fabricated working-looking links.
- 0 silent truncation or mixed-snapshot expansion.
- 100% routes enforce shared KRS/scope/freshness/budget policy.
- External MCP and Obsidian normalized packs are equivalent for equivalent
  inputs/snapshot.
- Direct factual Recall@5, nDCG@10, citation correctness/completeness, unsupported
  claim rate, and hard-negative behavior meet Program-1 approved tolerances.
- Target associative/global/agentic families improve by approved minimum before
  their enhanced routes are enabled.
- Every operation passes budget, provenance, snapshot, locator, degradation, and
  Reference Mode fixtures.
- Feedback lineage is complete and has zero silent source/ranking/truth mutation.
- Full local CI, migration rehearsal, and active testbed pass.

## Rollback Strategy

### Pre-Migration

- Back up copied/production DB according to approved migration spec.
- Record current schema/version, query/context contract fixtures, and baseline
  client outputs.
- Keep Plan-A route admissions independently disableable.

### During Migration

- Apply additive changes and verify forward/rollback on copied DB first.
- Verify existing query traces and plugin trace inspection remain readable or
  provide an explicit approved migration.
- Do not use permanent dual implementations.

### Failure Response

- Trace/snapshot/provenance/budget invariant failure: stop rollout and restore the
  last stable service/adapter path through the approved rollback.
- Route-specific quality/cost failure: disable only that route enhancement.
- Plugin parity/grounding failure: keep plugin on the last approved adapter until
  equivalence passes; do not inject untraceable fallback context.
- Three repeated QA failures: invoke `rollback_strategist`, restore the last
  stable release state, and return to planning.

## Stop Conditions

- Stop if Program 1 or Program 2 is not merged and verified.
- Stop if Plan A is unmerged or its retrieval-result, transaction, provenance,
  or locator handoff gates are incomplete.
- Stop if stable identity, minimal support, locators, or freshness are missing.
- Stop before coding until target specs/guides and migration plan are approved.
- Stop if compatibility requires a second retrieval truth path.
- Stop if a route cannot be bounded, traced, snapshot-consistent, or
  provenance-valid.
- Stop graph/agentic route adoption if it sacrifices factual quality beyond
  tolerance.
- Stop feedback integration if it can silently change source truth or ranking.

## Final Deliverables

- Approved static specs and synchronized English/Korean guides.
- Versioned ContextService request/response contracts.
- Root/child transaction and snapshot implementation.
- Progressive budgeted pack/expansion/verification operations.
- Unified MCP/CLI/backend synthesis/Obsidian adapters.
- Exact-pack Sources & Trace UX.
- Append-only feedback and promotion lineage.
- Frozen cross-client E2E and quality suite.
- Migration/rollback evidence.
- Versioned release and PR after all gates pass.

---

## Plan E P7 Research Handoff (2026-06-12)

Source: `backend/research_spikes/reports/p7.md`, `backend/research_spikes/manifests/p7.yml`.
Binding specification requirements handed off at Plan E P8; adoption still
flows through this plan's own phases, benchmarks, and gates.

### Adopted Contract: Progressive Context Disclosure (`adopt-contract`, confirmed at P7)

The ContextService MUST declare omissions and expose stable expansion handles
for every record it omits from a served context block. A silent fixed
character cutoff is a REJECTED DEFAULT (Wave C: fixed block and fixed top-k
silently dropped relevant evidence; progressive disclosure kept every omitted
relevant record recoverable at `1.00` recall with the highest context
precision). Coverage limitation recorded at P7: the research holdout contained
no disclosure-family case, so this confirmation is contract-level
(provenance/leakage audits + Wave C evidence); this plan's own E2E suite must
include disclosure cases.

### Contract Candidates: Bounded Iterative Retrieval Invariants (`benchmark-later`)

Any iterative retrieval loop MUST carry: an explicit maximum iteration count,
per-iteration budget accounting, a deterministic stop condition, and a single
snapshot per task (no mixing snapshots mid-loop). Wave C evidence: bounded
iteration completed the two/three-hop tasks one-shot could not (`0.67` vs
`0.00`), failed the four-hop case instead of looping, and never mixed
snapshots. Unbounded or snapshot-mixing iteration is a REJECTED DEFAULT.

### `benchmark-later` Inherited Postures

- Retrieval sufficiency / corrective gate: recall-limited by evaluator blind
  spots (Wave C SF03 false negative); any future gate is bounded to
  vault-evidence, single-snapshot correction and must measure gate
  precision/recall against an independent oracle.
- Complexity-aware routing: the P7 probe routed correctly, but the classifier
  remains a trivial regex with no measured overhead or real query
  distribution; benchmark on this plan's actual query mix before adoption.

### Plan D2 Program-1 Handoff (v0.7.0)

Consume `docs/specs/failure_atlas/PROGRAM_HANDOFFS.md`, especially F3/F4/F5/
F11/F12. Progressive disclosure and client parity must preserve the
authoritative QTR, exact source-span provenance, explicit omissions, and
per-family fine-grained evaluation.

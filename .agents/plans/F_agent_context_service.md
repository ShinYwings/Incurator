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

- Execution-start status recorded 2026-06-18 (Codex):
  `## feature/agent-context-service...origin/feature/agent-context-service`;
  modified: `.agents/ROADMAP.md`, `.agents/USER_REPORT.md`,
  `.agents/drafts/diff_viewer_plugin.md`; untracked:
  `.agents/drafts/chat_context_decay.md`,
  `.agents/drafts/popover_tool_scope.md`,
  `.agents/drafts/prompt_architecture_refactoring.md`.
- Work from a new Program-3 branch created from merged `master`.
- Do not revert, stage, or include unrelated user/agent changes.
- Update `RELAY.md` only when the approved workflow begins; this planning task
  does not modify it.

### P2 Implementation Evidence (2026-06-18, Codex)

- Added `backend/src/curator/context_service.py` as the first concrete
  `ContextService` boundary. `context_fetch` now owns the root `QTR-*`,
  deterministic `SNAP-*`, ordered `CTXA-*` child actions, `PACK-*` id,
  conservative budget accounting, and typed `snapshot_conflict` response.
- Updated `QueryOrchestrator.fetch_context` to delegate to `ContextService`
  while preserving legacy additive transport fields for existing MCP/plugin
  callers.
- Added strict P2 tests in
  `backend/tests/test_plan_f_context_service_contract.py` for module existence,
  exactly-one-root trace, ordered child actions, stable unchanged snapshot id,
  and no mixed-epoch conflict behavior.
- Added backend workspace hygiene guard in
  `backend/tests/test_workspace_hygiene.py` and test global-config isolation in
  `backend/tests/conftest.py`; `setup.sh` remains the service/runtime updater
  for repo-root `.venv`, while checks use repo-root `.venv-dev` through
  `scripts/backend-check`.
- Validation:
  - `scripts/backend-check pytest backend/tests/test_plan_f_context_service_contract.py backend/tests/test_query_orchestrator.py backend/tests/test_plan_a_retrieval.py -q`
    -> `30 passed`
  - `scripts/backend-check mypy`
    -> no issues in 95 source files
  - `scripts/backend-check ruff ...`
    -> passed
  - `scripts/backend-check pytest`
    -> `903 passed, 5 xfailed, 7 warnings`
  - `npx tsc --noEmit` and `npx vitest run` in `plugin/`
    -> passed (`44` files / `370` tests)

### Active Testbed And External References

- Available scenarios discovered 2026-06-18: `complex_math_backprop` and
  `testbed_template`. Active scenario remains unconfirmed; defer destructive
  `wiki testbed init --force` until P9 or an explicit scenario selection.

### P3 Pack/Budget Hardening Evidence (2026-06-18, Codex)

- Added `scripts/backend-check` as the canonical backend validation helper.
  It calls repo-root `.venv-dev/bin/{pytest,ruff,mypy,python}` directly, pins
  `mypy` stubs/cache to repo-root paths, and avoids `VIRTUAL_ENV` exports,
  `uv run --active`, `cd backend`, `backend/.venv`, and `backend/uv.lock`.
- Updated CI, PR template, AGENTS/CLAUDE rules, EN/KR agent workflow and
  contribution guides, Failure Atlas command references, and research-spike
  manifests to use `scripts/backend-check`.
- Extended workspace hygiene tests to forbid `backend/uv.lock`, require the
  helper, and reject reintroduced active-uv/export validation examples in the
  canonical agent and guide files.
- Extended `backend/tests/test_plan_f_context_service_contract.py` with P3
  pack contract tests for source-supported locator resolution, explicit budget
  omissions, trace/response selected-pack parity, and deterministic pack order.
- Hardened `ContextService.context_fetch` so selected pack items are budget
  bounded, omitted items are surfaced via `coverage.omitted_counts["budget"]`
  and `next` expansion handles, source-supported generated records inherit
  locators from their backing source spans, and the stored `QTR-*` trace matches
  the selected response pack.
- Added a source-section boundary fixture that preserves formula, code, and
  citation spans as separate pack items. The fixture exposed that
  `_span_items()` lost caller order after `WHERE id IN (...)`; retrieval now
  restores the original `span_ids` order before assembling items.
- Added global/source-section route tests that pin route-specific omissions:
  global packs now preserve both retrieval-level `global_reports` omissions and
  ContextService `budget` omissions, while source-section budget truncation
  keeps selected `source_span_ids` and the stored trace from mixing omitted
  spans back into the pack.
- Validation:
  - `bash -n scripts/backend-check` -> passed
  - `scripts/backend-check ruff` -> passed
  - `scripts/backend-check mypy` -> no issues in 95 source files
  - `scripts/backend-check pytest backend/tests/test_plan_f_context_service_contract.py backend/tests/test_workspace_hygiene.py -q`
    -> `16 passed`
  - `scripts/backend-check pytest` -> `904 passed, 6 skipped, 5 xfailed, 7 warnings`

### P4 Progressive Operations Evidence (2026-06-18, Codex)

- Added canonical P4 operation fixtures:
  `context_manifest.json`, `context_expand.json`, and `context_verify.json`
  under `docs/specs/system_behavior/context_service_fixtures/`, and updated the
  schema fixture registry text to include manifest, successful expand, and
  verify shapes.
- Extended `backend/tests/test_plan_f_context_service_contract.py` with P4
  tests for operation availability, manifest family summaries, stale snapshot
  conflict without trace mutation, expansion handle resolution, verification
  handle resolution, and `CTXA-*` child action append semantics.
- Implemented `ContextService.context_manifest`, `context_expand`, and
  `context_verify`. Progressive operations reuse the root `QTR-*`, enforce the
  stored `SNAP-*` id, return typed snapshot conflicts without mutation, and
  append ordered child actions only on successful expansion/verification.
- `context_fetch` now stores selected and omitted item payloads in the root
  context trace so later expansion/verification resolves the exact same
  pack/snapshot payload without re-running retrieval or mixing epochs.
- Validation:
  - `scripts/backend-check pytest backend/tests/test_plan_f_context_service_contract.py -q`
    -> `19 passed`
  - `scripts/backend-check ruff` -> passed
  - `scripts/backend-check mypy` -> no issues in 95 source files
  - `scripts/backend-check pytest` -> `910 passed, 6 skipped, 5 xfailed, 7 warnings`

### P5 Public Adapter Parity Evidence (2026-06-18, Codex)

- Extended `backend/tests/test_mcp_tools.py` so the public
  `curator_fetch_context` MCP tool must return the normalized ContextService
  pack shape (`operation=context_fetch`, `contract_version`, `PACK-*`,
  `SNAP-*`, `RTR-*`, item expansion/verification handles) while still omitting
  backend-synthesized `answer`.
- The MCP test also verifies that the returned `QTR-*` root trace contains the
  same `retrieval_trace.context_service.pack_id` and snapshot id as the public
  response, proving the MCP adapter is not assembling a second context path.
- No implementation change was needed for this slice because
  `curator_fetch_context` already delegates through `QueryOrchestrator`, and
  `QueryOrchestrator.fetch_context` delegates to `ContextService`.
- Refactored `QueryOrchestrator.run` for non-explore answer routes so
  `curator_query`/`wiki query` first obtain a ContextService pack, synthesize
  only over that exact selected pack, and append a `synthesis` child action to
  the same root `QTR-*` trace instead of building an independent answer
  evidence path. Explore mode remains on the existing explore pipeline pending
  its later bounded-followup work.
- Extended `backend/tests/test_query_orchestrator.py` to require synthesized
  local answers to keep the ContextService `PACK-*`/`SNAP-*` trace payload and
  record the prompt run as a `synthesis` `CTXA-*` child action.
- Migrated the MCP `curator_query` L3-complete path from legacy
  `query.run_query` to `QueryOrchestrator.run`, preserving legacy
  `ok`/`answer`/`question`/`trace` fields while adding `trace.pack_id`,
  `trace.snapshot`, `trace.budget`, `trace.source_span_ids`, and
  `trace.prompt_trace_ids`. The L3-incomplete degraded fallback remains
  unchanged for now.
- Updated `SYSTEM_BEHAVIOR.md` and EN/KR MCP guides so the public
  `curator_query` trace contract documents the Plan F additive fields.
- Validation:
  - `scripts/backend-check pytest backend/tests/test_mcp_tools.py::V031McpToolsTests::test_fetch_context_evidence_only -q`
    -> `1 passed`
  - `scripts/backend-check pytest backend/tests/test_query_orchestrator.py -q`
    -> `7 passed`
  - `scripts/backend-check pytest backend/tests/test_mcp_tools.py backend/tests/test_query_orchestrator.py -q`
    -> `14 passed`
  - `scripts/backend-check ruff` -> passed
  - `scripts/backend-check mypy` -> no issues in 95 source files
  - `scripts/backend-check pytest` -> `911 passed, 6 skipped, 5 xfailed, 7 warnings`

### P5 Plugin JSON Adapter Evidence (2026-06-18, Codex)

- Migrated `plugin_api.curator_query` L3-complete path from the legacy
  `query.run_query` side path to `QueryOrchestrator.run`, so hidden
  `wiki plugin query` now shares the same ContextService-backed `QTR-*`,
  `PACK-*`, `SNAP-*`, selected pack budget, prompt trace ids, and source span
  provenance as MCP `curator_query`.
- Preserved the existing L3-incomplete degraded fallback for now; F12's oracle
  for normalized fallback parity remains explicitly xfailed until that degraded
  route is migrated.
- Added backend tests requiring plugin query language bridge and hidden CLI JSON
  responses to expose ContextService trace fields at both the additive result
  level and inside `trace`.
- Extended plugin `CuratorQueryResult`/`CuratorQueryTrace` types and
  `IncuratorClient` normalization so `pack_id`, `snapshot`, and `budget` are
  retained for the later Sources & Trace rendering slice.
- Updated plugin schema plus EN/KR plugin guides and system behavior docs for
  L3-complete plugin query ContextService parity.
- Validation:
  - `scripts/backend-check pytest backend/tests/test_plugin_query_language.py backend/tests/test_plugin_cli.py::test_plugin_query_returns_context_service_trace_fields backend/tests/test_mcp_tools.py backend/tests/test_query_orchestrator.py -q`
    -> `20 passed`
  - `npx tsc --noEmit` from `plugin/` -> passed
  - `npx vitest run src/agent/incuratorClient.test.ts` from `plugin/`
    -> `24 passed`
  - `scripts/backend-check ruff` -> passed
  - `scripts/backend-check mypy` -> no issues in 95 source files
  - `npx vitest run` from `plugin/` -> `44` files / `370` tests passed
  - `scripts/backend-check pytest -q` -> `915 passed, 6 skipped, 5 xfailed, 7 warnings`

### P5 Adapter Parity Tightening (2026-06-18, Codex)

- Added a plugin API parity regression proving L3-complete
  `plugin_api.curator_query` does not call the legacy `search.query` fallback,
  emits identical `pack_id`/`snapshot`/`budget`/`prompt_trace_ids` at the
  result and nested trace levels, and stores exactly one root `QTR-*` with a
  ContextService synthesis child action.
- Tightened the hidden `wiki plugin query` JSON regression with the same
  result-level/nested-trace parity and stored root trace checks.
- Kept explore mode explicitly out of P5 ContextService migration. Current tests
  require explore routes to return `null` pack metadata until the deferred
  explore migration phase is planned.
- Validation:
  - `scripts/backend-check pytest backend/tests/test_plugin_query_language.py::test_curator_query_l3_complete_uses_single_context_service_root backend/tests/test_plugin_cli.py::test_plugin_query_returns_context_service_trace_fields -q`
    -> `2 passed`
  - `scripts/backend-check pytest backend/tests/test_plugin_query_language.py backend/tests/test_plugin_cli.py::test_plugin_query_returns_context_service_trace_fields backend/tests/test_mcp_tools.py backend/tests/test_query_orchestrator.py -q`
    -> `21 passed`
  - `scripts/backend-check ruff` -> passed
  - `scripts/backend-check mypy` -> no issues in 95 source files

### P6 Provider Evidence-Pack Grounding Slice (2026-06-18, Codex)

- Added hidden plugin JSON command
  `wiki plugin context fetch --query ... --workspace-path ... --limit-tokens ...`
  as the local Obsidian equivalent of MCP `curator_fetch_context`. It returns
  the normalized `context_fetch` pack and does not synthesize or return an
  `answer`.
- Added `IncuratorClient.fetchContext()` plus normalized pack/item/evidence
  TypeScript contracts.
- Changed the default sidechat provider-context path from backend
  `curatorQuery` answer injection to ContextService evidence-pack grounding via
  `client.fetchContext()` and `formatCuratorContextPack()`.
- Preserved Sources & Trace metadata by adapting the fetched pack into the
  existing trace panel shape (`trace_id`, `pack_id`, `snapshot`, `budget`,
  provenance ids, warnings) without adding prompt trace ids for non-synthesis
  fetches.
- Kept `curatorQuery` available for explicit backend synthesis and compatibility,
  but it is no longer the ordinary provider-grounding path.
- Updated plugin schema, system behavior spec, and EN/KR plugin guides for the
  hidden context fetch command and no-default-backend-answer rule.
- Validation:
  - `scripts/backend-check pytest backend/tests/test_plugin_cli.py::test_plugin_context_fetch_returns_evidence_pack_without_answer -q`
    -> `1 passed`
  - `scripts/backend-check pytest backend/tests/test_plugin_cli.py::test_plugin_context_fetch_returns_evidence_pack_without_answer backend/tests/test_plugin_query_language.py backend/tests/test_plugin_cli.py::test_plugin_query_returns_context_service_trace_fields backend/tests/test_mcp_tools.py backend/tests/test_query_orchestrator.py -q`
    -> `22 passed`
  - `npx tsc --noEmit` from `plugin/` -> passed
  - `npx vitest run` from `plugin/` -> `44` files / `373` tests passed
  - `scripts/backend-check ruff` -> passed
  - `scripts/backend-check mypy` -> no issues in 95 source files
  - `scripts/backend-check pytest -q` ->
    `922 passed, 6 skipped, 5 xfailed, 7 warnings`
  - Workspace hygiene check found no backend-local `.venv`, `.venv-dev`,
    backend-local tool cache, or `uv.lock` artifact.

### P6 Sources & Trace Exact-Pack Rendering Slice (2026-06-19, Codex)

- Preserved the fetched ContextService pack on the local plugin trace payload as
  `context_pack` so Sources & Trace can render the exact pack used for provider
  grounding instead of reconstructing provenance from partial id arrays.
- Extended `renderCuratorQueryTrace()` with pack rendering for `pack_id`,
  snapshot id, budget, coverage/degraded state, item summaries, truth/freshness
  state, locators, expansion handles, verification handles, and omitted `next[]`
  expansion handles.
- Added source-contract UI tests for pack rendering and explicit degraded /
  `snapshot_conflict` display.
- Updated plugin schema, system behavior spec, and EN/KR plugin guides to
  document `context_pack` and exact-pack Sources & Trace rendering.
- Validation:
  - `npx vitest run src/ui/incuratorQueryTraceV031.test.ts src/ui/chatSidebarSource.test.ts src/context/providerContextFormat.test.ts src/agent/incuratorClient.test.ts`
    -> `4` files / `56` tests passed
  - `npx tsc --noEmit` from `plugin/` -> passed
  - `npx vitest run` from `plugin/` -> `44` files / `375` tests passed
  - Workspace hygiene check found no backend-local `.venv`, `.venv-dev`,
    backend-local tool cache, or `uv.lock` artifact.

### P6 Locator And Follow-Up Operation Slice (2026-06-19, Codex)

- Made Sources & Trace locators actionable. Vault locators render as clickable
  links and open `relpath` plus heading or block anchor when available; external
  locators open `external_uri`; unavailable locators remain inert/degraded text.
- Added hidden plugin JSON commands for follow-up ContextService operations:
  `wiki plugin context expand` and `wiki plugin context verify`. Both require
  the displayed root `PACK-*` and `SNAP-*` to avoid mixed-snapshot evidence.
- Added `IncuratorClient.expandContext()` and `IncuratorClient.verifyContext()`.
- Added Sources & Trace `Expand` and `Verify` controls for item handles. The
  trace panel dispatches explicit `context:expand` / `context:verify` events,
  and `chatSidebar` handles them through `IncuratorClient`, merges successful
  expansion items into the displayed `context_pack`, removes consumed expansion
  handles, and re-renders without forcing the chat to the bottom.
- Updated plugin schema, system behavior spec, and EN/KR plugin guides for
  clickable locators plus context expand/verify operations.
- Validation:
  - `scripts/backend-check pytest backend/tests/test_plugin_cli.py::test_plugin_context_fetch_returns_evidence_pack_without_answer backend/tests/test_plugin_cli.py::test_plugin_context_expand_and_verify_use_existing_pack -q`
    -> `2 passed`
  - `scripts/backend-check pytest backend/tests/test_plugin_cli.py::test_plugin_context_fetch_returns_evidence_pack_without_answer backend/tests/test_plugin_cli.py::test_plugin_context_expand_and_verify_use_existing_pack backend/tests/test_plugin_query_language.py backend/tests/test_mcp_tools.py backend/tests/test_query_orchestrator.py -q`
    -> `22 passed`
  - `npx vitest run src/agent/incuratorClient.test.ts src/ui/incuratorQueryTraceV031.test.ts src/ui/chatSidebarSource.test.ts`
    -> `3` files / `51` tests passed
  - `npx vitest run` from `plugin/` -> `44` files / `379` tests passed
  - `npx tsc --noEmit` from `plugin/` -> passed
  - `scripts/backend-check ruff` -> passed
  - `scripts/backend-check mypy` -> no issues in 95 source files
  - `scripts/backend-check pytest -q` ->
    `923 passed, 6 skipped, 5 xfailed, 7 warnings`
  - Workspace hygiene check found no backend-local `.venv`, `.venv-dev`,
    backend-local tool cache, or `uv.lock` artifact.

### P6 Snapshot-Conflict Refetch UX Slice (2026-06-19, Codex)

- Preserved `snapshot_conflict` metadata from backend context expand/verify
  responses in `IncuratorClient.normalizeContextPack()`: `error_type`,
  `expected_snapshot_id`, `current_snapshot_id`, and `resolution`.
- Extended Sources & Trace degraded-state rendering with a stale-pack
  **Refetch** control. The panel shows expected/current snapshot ids for
  conflicts and dispatches `context:refetch`.
- Extended `chatSidebar` context action handling so expand/verify snapshot
  conflicts mark the currently displayed pack stale instead of merging any
  returned evidence. Refetch re-runs `client.fetchContext()` for the original
  question and replaces the displayed `context_pack`, result ids, trace pack id,
  snapshot, and budget.
- Added trace panel CSS for pack rows, action buttons, stale/refetch controls,
  and long id wrapping so pack controls stay stable in compact Sources & Trace
  layouts.
- Updated plugin schema, system behavior spec, and EN/KR plugin guides for the
  stale/refetch-required snapshot conflict UX and the no mixed-snapshot merge
  rule.
- Validation:
  - `npx tsc --noEmit` from `plugin/` -> passed
  - `npx vitest run src/agent/incuratorClient.test.ts src/ui/incuratorQueryTraceV031.test.ts src/ui/chatSidebarSource.test.ts -c ./vitest.config.ts` from `plugin/`
    -> `3` files / `54` tests passed
  - `npx vitest run -c ./vitest.config.ts` from `plugin/` ->
    `44` files / `382` tests passed
  - `scripts/backend-check ruff` -> passed
  - `scripts/backend-check mypy` -> no issues in 95 source files
  - `scripts/backend-check pytest backend/tests/test_spec_sync.py backend/tests/test_workspace_hygiene.py -q`
    -> `12 passed`
  - `git diff --check` -> passed
  - Workspace hygiene check found no backend-local `.venv`, `.venv-dev`,
    backend-local tool cache, or `uv.lock` artifact.
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
uv venv "$(git rev-parse --show-toplevel)/.venv-dev"
uv pip install --python "$(git rev-parse --show-toplevel)/.venv-dev/bin/python" \
  -e "$(git rev-parse --show-toplevel)/backend[dev,mcp]"
scripts/backend-check pytest
scripts/backend-check ruff
scripts/backend-check mypy
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

---

## Batch 1-3 Audit Remediation Evidence (2026-06-18)

Source drafts: `.agents/drafts/batch_1_to_3_audit/00_overview.md` through
`10_micro_expansion_state_leak.md`.

### Fact-Check Classification

- `01_systemic_oracle_overfitting.md`: confirmed as a systemic evaluation
  risk, not a directly patchable implementation bug in this slice. It remains
  a planning requirement for real-world sampling, noise injection, and
  independent quality gates.
- `02_systemic_graph_fragmentation.md`: confirmed as a systemic graph-quality
  risk. It remains a planning requirement for soft-link strategy and graph
  density alerts.
- `03_systemic_pipeline_fragility.md`: confirmed as a systemic durability and
  conflict-UX risk. It remains a planning requirement for soft snapshots and
  integrity-worker behavior.
- `04_arch_locator_coupling.md`: confirmed as a code defect. Payload truth
  state now distinguishes orphaned support from source-supported evidence when
  the locator is unavailable.
- `05_arch_budget_thrashing.md`: confirmed as a code defect. Expansion
  refusals now return in `expansion_refused` and are not requeued as retryable
  `next` handles under the same budget.
- `06_arch_explore_bypass.md`: confirmed as a larger architectural migration
  gap. Explore route unification with ContextService is deferred to a planned
  route-migration phase, not hot-patched here.
- `07_arch_trace_mutation.md`: confirmed as a nuanced trace/provenance bug.
  Retrieval pack provenance is preserved under `retrieval_trace.context_service`;
  answer/result provenance is restricted to spans actually cited by validated
  synthesis output, and is cleared when synthesis validation fails.
- `08_micro_token_cjk_overflow.md`: confirmed as a code defect. The token
  estimator now uses a conservative max of character and UTF-8 byte estimates.
- `09_micro_deterministic_reordering.md`: confirmed as a code defect. Selected
  provenance arrays preserve pack first-occurrence order instead of sorting.
- `10_micro_expansion_state_leak.md`: confirmed as a code defect. Successful
  expansion consumes handles once, and already-selected handles do not append
  duplicate child actions.

### Implemented Contract Updates

- `ContextService.context_fetch` and expansion payloads preserve deterministic
  pack order for selected source spans, reports, synthesis nodes, and memory
  paths.
- Missing/unavailable locators with declared support are represented as
  `truth_state="orphaned_support"` and stale evidence instead of falsely
  marking the item source-supported.
- `context_expand` no longer leaks state across repeated requests: selected
  handles move from omitted to selected state, already-selected handles return a
  warning without adding trace actions, and budget-blocked handles are reported
  as refused rather than requeued.
- Successful synthesis records only validated prompt-output cited spans at the
  result/root-trace level; the full selected pack remains under
  `retrieval_trace.context_service`.
- Synthesis validation failure clears result/root-trace answer reference arrays.
  Failed synthesis is represented on the synthesis child action with empty cited
  spans while the retrieved pack remains inspectable under ContextService trace.
- ContextService-backed trace readers tolerate legacy `retrieval_trace = null`.
- `_context_evidence_block` joins the full already-budgeted pack without a
  secondary character cap and does not render JSON null values as literal
  `"None"`.
- English and Korean MCP guides document one-shot expansion handles and
  `expansion_refused`; system behavior spec documents CJK budgeting, ordering,
  orphaned support, expansion state, and failed synthesis trace semantics.

### Validation

- `scripts/backend-check pytest backend/tests/test_plan_f_context_service_contract.py::test_context_service_cjk_budget_estimator_is_conservative backend/tests/test_plan_f_context_service_contract.py::test_context_service_selected_refs_preserve_pack_order backend/tests/test_plan_f_context_service_contract.py::test_context_service_marks_orphaned_support_without_false_truth_state backend/tests/test_plan_f_context_service_contract.py::test_context_expand_reports_budget_refusals_without_requeueing_same_handles backend/tests/test_plan_f_context_service_contract.py::test_context_expand_consumes_successful_handles_once backend/tests/test_query_orchestrator.py::test_failed_answer_validation_preserves_retrieval_provenance -q`
  -> `6 passed`
- `scripts/backend-check pytest backend/tests/test_plan_f_context_service_contract.py backend/tests/test_query_orchestrator.py backend/tests/test_mcp_tools.py -q`
  -> `41 passed`
- `scripts/backend-check ruff` -> passed
- `scripts/backend-check mypy` -> no issues in 95 source files
- `scripts/backend-check pytest -q` ->
  `920 passed, 6 skipped, 5 xfailed, 7 warnings`
- Workspace hygiene check: `find backend -maxdepth 2 ...` found no forbidden
  backend-local `.venv`, `.venv-dev`, tool cache, or `uv.lock` artifact.

### Reviewer Provenance Remediation (2026-06-19, Codex)

- Removed the remaining synthesis evidence-block hazards: no hardcoded 16k
  truncation, no dropped budgeted items, and no literal `"None"` output for null
  pack fields.
- Hardened `curator_query`, plugin query, ContextService, and synthesis trace
  update code against persisted `retrieval_trace_json = null`.
- Fixed successful answer provenance so `result.source_span_ids` and root
  `QTR-*` `source_span_ids` reflect the validated prompt output's cited spans
  instead of the full retrieved pack.
- Fixed failed synthesis provenance so result/root answer reference arrays are
  cleared, while the full retrieved pack remains in
  `retrieval_trace.context_service.selected_items` and the synthesis child action
  records `synthesis_status=failed` with empty cited spans.
- Updated `SYSTEM_BEHAVIOR.md` plus EN/KR MCP guides to document cited-answer
  provenance versus full pack provenance.

Validation:

- `scripts/backend-check pytest backend/tests/test_query_orchestrator.py::test_context_evidence_block_does_not_render_none_values backend/tests/test_query_orchestrator.py::test_context_evidence_block_joins_all_budgeted_items_without_truncation backend/tests/test_query_orchestrator.py::test_successful_answer_records_only_parsed_cited_spans backend/tests/test_query_orchestrator.py::test_failed_answer_validation_clears_answer_provenance backend/tests/test_query_orchestrator.py::test_synthesis_trace_update_tolerates_null_retrieval_trace -q`
  -> `5 passed`
- `scripts/backend-check pytest backend/tests/test_query_orchestrator.py backend/tests/test_mcp_tools.py backend/tests/test_plugin_query_language.py backend/tests/test_plugin_cli.py::test_plugin_query_returns_context_service_trace_fields -q`
  -> `24 passed`
- `scripts/backend-check ruff` -> passed
- `scripts/backend-check mypy` -> no issues in 95 source files
- `scripts/backend-check pytest -q` ->
  `926 passed, 6 skipped, 5 xfailed, 7 warnings`
- `npx tsc --noEmit` from `plugin/` -> passed
- `npx vitest run -c ./vitest.config.ts` from `plugin/` ->
  `44` files / `379` tests passed
- `git diff --check` -> passed
- Workspace hygiene check found no backend-local `.venv`, `.venv-dev`, tool
  cache, or `uv.lock` artifact.

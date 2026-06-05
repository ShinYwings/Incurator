# Goal: Verified CLI Consolidation And Legacy Cleanup Implementation Plan

Date: 2026-06-04

Status: **awaiting user approval before docs/tests/code edits**

Source analysis:

- `.agents/plans/2026-06_cli_consolidation_and_legacy_cleanup.md`
- `.agents/plans/2026-06_deep_analysis/Phase_[A-K]_*.md`
- `docs/specs/curator_schema/SCHEMA_v0.3.1.md`
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.3.1.md`
- `docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.3.1.md`
- `docs/guides/WORKFLOW_GUIDE.md`
- `docs/guides/MCP_USER_GUIDE.md`

## 1. Scope Correction

The originally named `.agents/plans/2026-06_legacy_cleanup_plan.md` is not the
right target for this goal. It only describes leftover Gemini fallback cleanup.
The correct target is:

```text
.agents/plans/2026-06_cli_consolidation_and_legacy_cleanup.md
```

This plan treats the CLI/MCP/docs/DAG/GraphRAG diagnosis in that file as the
input, then verifies it against code, active specs, tests, and current Microsoft
GraphRAG documentation.

## 2. Verified Findings

### 2.1 Microsoft GraphRAG Verdict

The claim that Incurator "already has GraphRAG" is **structurally true but
operationally overstated**.

Confirmed:

- `state.sqlite` has GraphRAG-style records: `graph_entities`,
  `graph_relations`, `community_reports`, `memory_paths`, and
  `synthesis_nodes`.
- The v0.3.1 compile pipeline runs:
  `source_spans -> knowledge_units -> graph entities/relations -> community_reports -> synthesis_nodes`.
- Query orchestration has local/global/explore/source-section routing and
  combines DB graph evidence with qmd hits.

Not confirmed:

- Incurator does **not** use Microsoft's `graphrag` Python package.
- No dependency, import, or API call to Microsoft GraphRAG exists in the backend.
- Community detection is currently a custom connected-components pass, not
  Microsoft GraphRAG's indexing infrastructure.
- Search is still qmd shell-out over `.curator/Collections`, not Microsoft
  GraphRAG query infrastructure.

External reference check:

- Microsoft GraphRAG is an indexing/query pipeline for extracting entities,
  relationships, claims, communities, reports, and embeddings from unstructured
  text.
- Its query engine is explicitly organized around Local Search, Global Search,
  DRIFT Search, Basic Search, and question generation.
- Its default outputs are storage/vector-store oriented and configurable through
  provider factories.
- Official docs also warn that indexing can be expensive and the GitHub README
  identifies the code as a demonstration, not an officially supported Microsoft
  offering.

Recommendation:

```text
Do not adopt Microsoft GraphRAG as a direct runtime dependency now.
Use it as a reference architecture and selectively borrow mechanisms.
```

Rationale:

- Incurator's product requirements are not generic GraphRAG:
  Obsidian vault locality, source truth protection, Reference Mode, `curate.yml`
  KRS, MCP/plugin split, `02_Wiki/` promotion, and correction-driven backprop.
- The current DB IR already encodes most needed GraphRAG-like structures.
- Direct replacement would create a second indexing product beside the Curator
  compiler and would fight the source-span/provenance contract.

What to borrow:

- Better community detection later, likely Leiden or another graph clustering
  method, behind Incurator's `community_reports` contract.
- More mature local/global/DRIFT-style query routing.
- Prompt tuning and provider abstraction ideas.
- Incremental invalidation discipline for reports and derived synthesis nodes.

What not to borrow directly:

- Microsoft GraphRAG storage model as the authoritative state.
- Generic community reports as a replacement for Incurator's `SYN-` synthesis
  and dynamic curation lens.
- A second GraphRAG CLI/config surface inside the vault.

### 2.2 Current Search Decision

Phase H argues for replacing qmd with SQLite FTS5. That argument is plausible,
but it conflicts with the active v0.3.1 spec, which still defines qmd as the
search engine over derived markdown projections.

Current verified state:

- `search.py` shells out to qmd for update/embed/query.
- `retrieval/evidence.py` uses qmd as fallback and as part of local retrieval.
- `SYSTEM_BEHAVIOR_v0.3.1.md` explicitly says qmd remains the fallback retrieval
  engine.
- Selected v0.3.1 tests pass against this architecture.

Decision for this implementation:

```text
Do not replace qmd with FTS5 in this cleanup pass.
```

Reason:

- FTS5 replacement is a real architectural change, not a cleanup.
- It needs its own spec-first goal because it changes indexing, query scoring,
  CLI output, MCP status, testbed smoke behavior, and qmd config semantics.
- The immediate user-facing breakages are stale CLI/MCP/docs surfaces, not qmd
  itself.

### 2.3 Critical Drift Confirmed

P0 issues:

- `wiki curate` is removed from the current CLI, but still appears in specs,
  guides, CLI hints, and workspace rule templates.
- `curator_curate_workspace` is referenced by generated workspace rules, but no
  MCP tool with that name exists.
- `curator_get_curation_plan` is documented but not implemented; the implemented
  MCP tool is `curator_plan_workspace`.
- MCP `curator_sync` appears to call `build_client` with a stale signature.
- MCP `curator_lint` appears to call `LintReport` properties as methods.

P1 issues:

- L4 naming is split: v0.3.1 says frozen `EXH-` is removed and active L4 is
  `SYN-` under `04_Synthesis`, but constants/config/lint/MCP still contain
  active `EXH-` assumptions.
- `dag_edges` still documents `CON -> EXH`, while the v0.3.1 active model is
  closer to `CTX -> ATM`, `ATM/KNU -> CON/REP`, `REP/CON -> SYN`, with
  `artifact_dependencies` as the stronger invalidation primitive.
- `wiki query --help` still documents an empty route as "legacy qmd synthesis,"
  despite the clean-rebuild spec saying there is no legacy query fallback path.
- Guides still describe `search_curator` as auto-running `wiki curate`, which is
  no longer accurate.
- Some old Gemini fallback cleanup items are already done, while capacity error
  surfacing remains valid and should not be deleted.

## 3. Decisions Needed Before Implementation

These should be confirmed before coding. If there is any doubt, run `/grill-me`
against these exact questions.

1. **L4 contract**
   - Recommended: active L4 is `SYN-` / `04_Synthesis`.
   - `EXH-` files are inert legacy or explicit promoted historical artifacts, not
     active DAG nodes.

2. **Top-level `wiki curate`**
   - Recommended: do not restore top-level `wiki curate` in this cleanup.
   - Replace stale references with `wiki build`, `wiki query --route ...`,
     `wiki plugin curate plan`, and MCP `curator_plan_workspace`.

3. **MCP curation plan name**
   - Recommended: keep the implemented `curator_plan_workspace` as the canonical
     tool.
   - Remove `curator_get_curation_plan` from specs/docs unless a read-only lookup
     is explicitly needed later.

4. **Search backend**
   - Recommended: keep qmd for this pass.
   - Defer FTS5 replacement to a separate goal with its own specs/tests.

5. **Dependency graph**
   - Recommended: treat `artifact_dependencies` as the authoritative invalidation
     mechanism for v0.3.1 generated DB artifacts.
   - Keep `dag_edges` only for page/projection traversal where it is actually
     maintained, or update it narrowly if tests prove existing commands require it.

## 4. Implementation Plan After Approval

### Phase 1: Docs/Specs Reconciliation

Verify:

```bash
rg -n "wiki curate|wiki refresh|curator_curate_workspace|curator_get_curation_plan|EXH-|04_Exhibitions|legacy qmd" docs backend/src/curator/workspace/templates
```

Edits:

- Update `docs/specs/curator_schema/SCHEMA_v0.3.1.md`
  - Remove `EXH-` from the active valid-prefix list or label it explicitly as
    inert legacy.
  - Reconcile §11 storage model language that says L4 Exhibitions are the only
    human/agent-facing artifact with §15, which says frozen Exhibitions are
    removed.
  - Clarify `SYN-` / `04_Synthesis` as active L4 projection.

- Update `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.3.1.md`
  - Remove stale `wiki curate validate`, `wiki curate plan`, and
    `wiki curate --workspace` from the active public CLI surface unless the user
    rejects the recommendation above.
  - Replace them with the actual active surfaces:
    `wiki plugin curate plan`, MCP `curator_plan_workspace`,
    `curator_validate_curate_spec`, `curator_fetch_context`, and
    `curator_query`.
  - Clarify that qmd is retained as internal retrieval backend/fallback for this
    version.

- Update `docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.3.1.md`
  - Ensure plugin-local JSON commands match the implemented `wiki plugin ...`
    surface.
  - Keep MCP as external-agent interface only.

- Update guides in English first, then matching Korean guides:
  - `docs/guides/WORKFLOW_GUIDE.md`
  - `docs/guides/WORKFLOW_GUIDE_KR.md`
  - `docs/guides/MCP_USER_GUIDE.md`
  - `docs/guides/MCP_USER_GUIDE_KR.md`
  - `docs/guides/AGENT_WORKFLOW_GUIDE.md` if present/active

Success criteria:

- No active guide/spec says users should call top-level `wiki curate`.
- No workspace agent guide tells agents to call `curator_curate_workspace`.
- Tool names in docs match implemented or intentionally planned MCP tools.

### Phase 2: Tests First

Add or update focused backend tests before code changes:

- CLI surface tests:
  - `wiki --help` includes daily commands but not hidden integration groups.
  - `wiki curate --help` fails or is absent if the no-top-level-curate decision is
    approved.
  - `wiki plugin curate plan --help` remains available.

- Workspace template tests:
  - Generated `AGENTS.md`, `CLAUDE.md`, and workflow templates do not mention
    `curator_curate_workspace`.
  - They recommend `curator_plan_workspace`, `curator_fetch_context`, or
    `curator_query` depending on the flow.

- MCP tests:
  - `curator_sync` returns a valid result and does not call `build_client` with a
    stale signature.
  - `curator_lint` returns valid health/error data using properties correctly.
  - `curator_plan_workspace` is documented and callable.
  - No test expects `curator_get_curation_plan` unless that tool is deliberately
    added.

- L4 contract tests:
  - `COLLECTION_LAYERS` includes active `04_Synthesis` if required by qmd.
  - `curator_get_node` can retrieve active `SYN-` projections or explicitly does
    not promise node retrieval for SQL-only synthesis records.
  - Lint treats `SYN-` as active and `EXH-` as legacy/inert according to the
    approved decision.

- Legacy Gemini cleanup guard:
  - No `google-generativeai` dependency in `backend/pyproject.toml` or
    `backend/uv.lock`.
  - No `_get_antigravity_fallback_chain`.
  - Antigravity capacity detection remains tested and not removed.

Success criteria:

```bash
cd backend
uv run pytest tests/test_v031_db_schema.py \
  tests/test_v031_compile_pipeline.py \
  tests/test_v031_query_router.py \
  tests/test_v031_query_route.py \
  tests/test_v031_memory_paths.py
```

The selected baseline already passed locally: **29 passed in 0.84s**.

### Phase 3: Code Cleanup

Edits should be surgical and limited to confirmed drift:

- CLI hints and help text:
  - Replace remaining user-facing `wiki curate` hints with `wiki build`,
    `wiki query`, or `wiki plugin curate plan`.
  - Remove "legacy qmd synthesis" language from `wiki query --help` if
    `QueryOrchestrator` is the default route.

- Workspace templates:
  - Replace `curator_curate_workspace` with the approved MCP flow.
  - Ensure generated templates tell agents to call `curator_check_workspace`
    first, then `curator_plan_workspace` or `curator_fetch_context` when needed.

- MCP implementation:
  - Fix `curator_sync` stale `build_client` call.
  - Fix `curator_lint` property/method mismatch.
  - Keep `curator_plan_workspace` as canonical, or add a read-only alias only if
    explicitly approved.

- L4 naming:
  - Update constants/config/lint/MCP only where tests prove active behavior is
    wrong.
  - Prefer adding `04_Synthesis`/`SYN-` support over deleting legacy paths blindly.
  - Preserve inert legacy reads if they are needed to avoid breaking old vaults,
    but do not advertise them as active v0.3.1 flow.

- Gemini fallback residue:
  - Remove stale RAM auto-selection comments/helpers only if tests show they are
    unused.
  - Do not remove `_is_capacity_error` or Antigravity 429 surfacing; specs and
    existing tests require that behavior.

### Phase 4: Verification

Non-mutating checks:

```bash
cd backend
uv run pytest tests/test_v031_db_schema.py tests/test_v031_compile_pipeline.py tests/test_v031_query_router.py tests/test_v031_query_route.py tests/test_v031_memory_paths.py
uv run wiki --help
uv run wiki plugin --help
uv run wiki plugin curate --help
uv run wiki query --help
VAULT_ROOT=../testbed uv run wiki status
```

Repository-rule testbed validation after implementation:

```bash
cd backend
VAULT_ROOT=../testbed uv run wiki status
VAULT_ROOT=../testbed uv run wiki add
VAULT_ROOT=../testbed uv run wiki sync
VAULT_ROOT=../testbed uv run wiki lint
VAULT_ROOT=../testbed uv run wiki reindex
```

LLM-sensitive checks, if provider auth/capacity is available:

```bash
cd backend
VAULT_ROOT=../testbed uv run wiki build --wait
VAULT_ROOT=../testbed uv run wiki query "Summarize the core concepts in this vault." --route auto
```

Known blocker:

- The current `testbed/` is initialized and qmd is available, but it has 0 tracked
  sources. `wiki add` will mutate the testbed and is intentionally deferred until
  implementation approval.
- LLM-backed `wiki build --wait` and `wiki query` depend on provider auth and
  quota/capacity.

## 5. Approval Gate

Stop here until the user approves the plan or answers the decision questions.

Recommended approval text:

```text
Approve the no-top-level-curate / SYN-active / qmd-retained cleanup plan.
```

If any of the decisions in §3 are uncertain, run `/grill-me` before
implementation.

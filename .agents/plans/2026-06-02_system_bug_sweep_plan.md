# System Bug Sweep Plan - 2026-06-02

## Approval Gate

This is a `/goal` plan-first artifact. Per `AGENTS.md`, implementation must stop
here until the user approves the plan.

If the scope feels too broad or any behavior choice should be interrogated
before coding, use `/grill-me`. The highest-value questions for grilling are:

- whether `wiki init` persona setup should remain LLM-interview-based or become
  deterministic menu collection with optional LLM refinement;
- whether `.canvas` build traces should be disabled by default, moved under
  `.curator/staging/`, or kept only when a debug flag is set;
- whether the first implementation pass should prioritize CLI/backend
  correctness before plugin UI polish, or ship both together.

## Evidence Reviewed

- `.agents/plans/Untitled.md`
- `.agents/plans/Pasted image 20260602002147.png`
- `.agents/plans/Pasted image 20260602002204.png`
- `.agents/plans/Pasted image 20260602003645.png`
- `docs/specs/curator_schema/SCHEMA_v0.2.2.md`
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.2.2.md`
- `docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.2.2.md`
- `docs/guides/WORKFLOW_GUIDE.md`
- `docs/guides/PLUGIN_GUIDE.md`
- `.agents/plans/2026-06_query_exhibition_plan.md`
- `.agents/plans/2026-06_obsidian_agent_ux_performance_plan.md`
- `.agents/plans/2026-06-01_Math_RAG_Backprop_Plan.md`
- `scripts/dev/complex_math_backprop/MASTER_PLAN.md`

Screenshots show:

- Syncthing reports one current device (`MacOS`) plus one shared remote device
  (`shin`), while Incurator/device metadata appears to overcount or preserve
  stale state.
- The plugin AI Provider settings model dropdown falls back to `Custom...`
  instead of backend catalogue entries.

## Current Contracts That Already Answer Several Bugs

The active specs already require these behaviors:

- `wiki add` is registration plus instant structural L1 only; `wiki build`
  performs L2/L3; `wiki curate` creates L4.
- Plugin source state now uses layer-explicit readiness labels
  (`l1_ready`, `l2_ready`, `l3_ready`, `l4_ready`) instead of ambiguous
  `indexed`/`curated` labels for intermediate layers.
- `incuratorDefaultImportMode` must default to `"reference"`.
- Provider model choices must come from backend `get_available_models`, backed
  by `backend/src/curator/data/models.json`.
- Non-pinned line references, selections, and PDF snips must be primary focus
  for the current turn; pinned purple context is only background grounding.
- Query-generated Exhibitions should be saved for successful L3-grounded
  workspace queries and surfaced through trace.
- Syncthing discovery may record actual Syncthing facts only; backend launcher
  paths are per-device declarations in `.curator/devices.json`.

## Root Cause Hypotheses

### A. Init And Persona Wizard

Symptoms: Q2 multi-select unclear, persona chat does not exit, Korean/internal
language leakage, title behavior.

Likely code paths:

- `backend/src/curator/cli.py::_run_init_wizard`
- `backend/src/curator/cli.py::_run_curator_persona_wizard`
- `backend/src/curator/prompts.py`
- `plugin/src/ui/chatSidebar.ts::getSessionTitle`

Current risk:

- Persona setup depends on a free-form multi-turn LLM interview. The transcript
  shows the model emits `{"done": true, ...}` but the CLI does not echo a final
  success before returning, making the user think the chat is still open.
- Menu numbering shown to the user is global or reused awkwardly; multi-select
  support is not consistently advertised per question.
- `getSessionTitle` uses 44 characters, but the requested cap is 20 characters.

### B. Reset, Status, Sync Report, And `.canvas`

Symptoms: `wiki reset` leaves device/sidechat state, L2/L3 readiness shown with
ambiguous legacy labels,
blue/healthy status despite L3 error, repeated sync report after no edits,
`.curator/*.canvas` files clutter root.

Likely code paths:

- `backend/src/curator/cli.py::reset`
- `backend/src/curator/cli.py::status`
- `backend/src/curator/db.py`
- `backend/src/curator/mcp_server.py::_source_dict`
- `backend/src/curator/source_tools.py`
- `backend/src/curator/lint.py`
- `backend/src/curator/ingest_worker.py::_write_build_canvas`

Observed likely defects:

- Reset removes database and generated collections but not `.curator/devices.json`,
  `.curator/sessions.json`, dashboard/cache/sync report, or build trace canvases.
- MCP light source status used to map database `status in {"curated","done"}`
  to an ambiguous `"indexed"` state without deriving state from layer statuses
  first.
- Plugin `normalizeStatus` now turns `l3_complete` into `"l3_ready"` and
  `l4_status="done"` into `"l4_ready"`, matching the user's desired semantics.
- Build trace canvas writes to `.curator/build_trace_*.canvas`.
- Repeated sync-report findings likely come from orphan Context detection
  treating valid L1-only CTX pages as review findings after `wiki add`, despite
  v0.2.2 allowing L1 complete while L2/L3 are pending.

### C. Source Recall, RAG Focus, Language, And L4 Exhibition

Symptoms: L1/L2/L3 feel too thin, context pages preserve Korean raw text, English
questions receive Korean answers, crop/line questions answer pinned documents
instead of the selected region, Obsidian chat shows no Exhibition.

Likely code paths:

- `backend/src/curator/ingest_raw.py`
- `backend/src/curator/ingest_llm.py`
- `backend/src/curator/query.py`
- `backend/src/curator/mcp_server.py::curator_query`
- `plugin/src/context/chatContextPriority.ts`
- `plugin/src/context/systemPrompt.ts`
- `plugin/src/context/providerContextFormat.ts`
- `plugin/src/ui/chatSidebar.ts`

Important design constraint:

- L1 must preserve recall and source text. It should not replace source sections
  with a lossy LLM summary. A better fix is to keep raw `## Source Sections`
  for evidence traversal while improving `## Summary`, `## Key Claims`, and
  `## Atom Candidates` quality or adding optional LLM-enriched overlays during
  `wiki build`.

Likely defects:

- Prompt priority may still allow pinned/auto context to dominate primary
  snippets.
- Language instruction may exist in backend `query.py`, but plugin direct-chat
  prompts likely need the same "answer in user's language" rule.
- Query fallback and trace/exhibition rendering need to be checked against the
  existing `2026-06_query_exhibition_plan.md`.

### D. Syncthing Device And Zotero Reference Mode

Symptoms: device count looks wrong, stale remote device info persists, Zotero
external reference ingest produces no visible response.

Likely code paths:

- `plugin/src/utils/deviceRegistry.ts`
- `backend/src/curator/device_registry.py` or equivalent device helpers
- `backend/src/curator/cli.py::devices_sync`
- `plugin/src/ui/chatSidebar.ts::maybeOfferIncuratorIngest`
- `plugin/src/agent/incuratorClient.ts::registerSourceReference`
- Zotero MCP tools in `backend/src/curator/mcp_server.py`

Likely defects:

- Device registry merge preserves old devices but may not prune devices absent
  from current Syncthing shared folder membership.
- Plugin registers Zotero PDFs as references automatically, but notice/status
  output may not refresh or may swallow a backend error.
- External path resolution should be tested against actual Zotero storage paths,
  not copied files.

### E. Provider Model Catalogue And Backend Settings UI

Symptoms: provider model dropdown shows `Custom...`; backend enabled but status
  says "not configured"; default import mode is copy instead of reference.

Likely code paths:

- `plugin/src/types.ts::DEFAULT_SETTINGS`
- `plugin/main.ts::ensureIncuratorBackend`
- `plugin/main.ts::refreshAvailableModels`
- `plugin/src/agent/incuratorClient.ts::getAvailableModels`
- `plugin/src/settings.ts`
- `plugin/src/ui/incuratorDashboardModal.ts`
- `plugin/src/utils/incuratorBackendStatus.ts`

Confirmed defect:

- `DEFAULT_SETTINGS.incuratorDefaultImportMode` is currently `"copy"`, despite
  docs/spec requiring `"reference"`.

Likely defects:

- Settings UI is rendered before async model catalogue fetch completes and may
  not re-render after `availableModels` updates.
- Backend status may inspect loaded tools before the auto-created Incurator MCP
  server finishes starting, yielding "Not Configured" instead of "Waiting" or
  "Connected".

## Implementation Plan

### Phase 1 - Lock Contracts And Tests

1. Update specs/guides first:
   - Clarify L1/L2/L3/L4 status names and colors.
   - Clarify `wiki reset` scope, including whether chat sessions and devices are
     removed by default or via explicit flags.
   - Clarify `.canvas` build trace storage/default.
   - Clarify persona wizard selection rules and exit behavior.
   - Clarify source-section raw recall versus LLM summary/enrichment.
2. Add focused backend tests before code:
   - `wiki reset` removes selected `.curator` state without touching
     `config.yml`.
   - source status derives visible state from `l1/l2/l3/l4_status` and errors.
   - orphan CTX findings are suppressed or downgraded when L2/L3 are pending.
   - canvas traces are not written at `.curator/` root by default.
3. Add focused plugin tests before code:
   - default import mode is `reference`.
   - source status maps L3/L4/error exactly as revised contract says.
   - model catalogue refresh updates settings/default model from backend data.
   - selected/cropped context outranks pinned context in prompt assembly.
   - session title truncates to 20 characters.

### Phase 2 - Fix Backend CLI And State

1. Make persona init deterministic enough to exit:
   - accept declared multi-select answers where the question permits lists;
   - show single-select versus multi-select in the prompt text;
   - terminate immediately after valid `done=true` persona JSON is saved;
   - keep persisted persona fields in English/canonical enum form while allowing
     user-facing prompt text to match the terminal language.
2. Extend `wiki reset` with an explicit reset manifest:
   - always remove generated DAG/database/cache/report/dashboard/build traces;
   - decide through docs whether to remove `.curator/devices.json` and
     `.curator/sessions.json` by default or behind flags.
3. Repair source status:
   - centralize layer-to-state mapping in backend and reuse it for CLI/MCP.
   - error wins over healthy states.
   - only L4 done receives `l4_ready`.
4. Move or gate canvas trace generation:
   - default no root `.curator/build_trace_*.canvas`;
   - if retained, write under `.curator/staging/canvas/` or
     `.curator/Collections/_diagnostics/`.
5. Make sync reports idempotent:
   - repeated `wiki add`/`wiki build` with no content changes should not keep
     surfacing the same non-actionable review findings.

### Phase 3 - Fix Plugin Runtime/UI

1. Change `DEFAULT_SETTINGS.incuratorDefaultImportMode` to `"reference"` and add
   a migration for old missing/default values.
2. Ensure enabling Incurator backend creates the runtime server and reports
   "Waiting" while MCP tools load, not "Not Configured".
3. Fetch backend model catalogue on startup and on settings/dashboard open; rerender
   provider controls when catalogue arrives.
4. Align plugin source-state mapping and badges with backend.
5. Ensure selected line ranges, PDF snippets, and crop images are serialized as
   the primary focus in direct-chat and MCP-enhanced prompts.
6. Set chat titles from the first user answer/question, capped at 20 characters.
7. Surface Zotero reference-registration outcomes with a visible notice/status
   refresh and preserve any backend error text.

### Phase 4 - Improve Source Recall Without Losing Provenance

1. Keep raw `## Source Sections` intact as the source recall layer.
2. Improve generated L1 metadata sections:
   - richer structural summary;
   - better key claims and atom candidates;
   - English canonical headings/metadata;
   - source text preserved as-is, including Korean source text when the source
     itself is Korean.
3. Ensure MCP/document-section tools can traverse from L3/L4 down to L1 source
   sections and raw paths with page/section provenance.
4. Validate English input produces English output, Korean input produces Korean
   output, in both backend query and plugin direct-chat paths.

### Phase 5 - Validate In Testbed

Active scenario candidate:

- `scripts/dev/complex_math_backprop/`

Required baseline:

```bash
wiki testbed init complex_math_backprop --force
VAULT_ROOT=testbed wiki status
VAULT_ROOT=testbed wiki add
VAULT_ROOT=testbed wiki build --wait
VAULT_ROOT=testbed wiki sync
VAULT_ROOT=testbed wiki lint
```

If LLM/qmd is unavailable:

- run deterministic unit tests and non-LLM smoke checks;
- report the exact blocker;
- use the local simulated validation role only as a provisional signal.

Plugin verification:

```bash
npm test
npm run build
```

from `plugin/`, plus any focused Vitest files added in Phase 1.

Backend verification:

```bash
backend/.venv/bin/pytest backend/tests -q
```

or a narrower set first, then full backend tests if runtime permits.

## Out Of Scope For First Pass

- Replacing the entire L1 pipeline with a third-party proprietary "Ask Gemini"
  clone. The first fix should preserve Incurator's existing v0.2.2 contract:
  parser-first recall with optional LLM enrichment during deeper build.
- Deleting or rewriting `03_Notes/` or external Zotero source files.
- Making Syncthing itself sync faster or changing Syncthing folder topology.

## Stop Point

Stop here and wait for user approval before editing code, docs, or tests.

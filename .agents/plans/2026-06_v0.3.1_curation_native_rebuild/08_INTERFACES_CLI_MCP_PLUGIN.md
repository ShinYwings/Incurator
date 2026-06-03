# Interfaces Plan: CLI, MCP, Plugin JSON, And Trace

## 1. Purpose

v0.3.1 must expose the curation-native rebuild through clear public interfaces.
The same backend service functions should power CLI, MCP, and plugin JSON
commands.

MCP remains the external-agent interface. The Obsidian plugin uses local backend
JSON commands and runtime snapshots for same-device flows.

## 2. CLI Interfaces

### 2.1 Workspace Curation

Future CLI:

```bash
wiki curate plan --workspace PATH --json
wiki curate validate --workspace PATH
wiki curate prompts --workspace PATH
wiki curate --workspace PATH
```

Responsibilities:

- load `curate.yml`;
- validate KRS fields;
- build `CurationPlan`;
- show selected sources, exclusions, retrieval modes, and prompt profile;
- write/refresh Exhibition only for the final `curate` command.

### 2.2 Query

Future CLI:

```bash
wiki query "..." --workspace PATH --mode auto
wiki query "..." --workspace PATH --mode local
wiki query "..." --workspace PATH --mode global
wiki query "..." --workspace PATH --mode explore
```

Response should include trace when `--json` is used:

- route decision;
- source spans;
- concepts/entities/communities;
- prompt trace ids;
- active Exhibition;
- insight candidates.

### 2.3 Prompt Tools

Future CLI:

```bash
wiki prompt list
wiki prompt show curator.exhibition_write.v1
wiki prompt trace TRACE_ID
wiki prompt eval
```

These commands support debugging prompt regressions.

### 2.4 Backprop

Future CLI:

```bash
wiki sync --backward --target EXH-...
wiki sync --backward --dry-run --target EXH-...
```

Dry-run should return diagnosis and patch plan without writing generated nodes.

## 3. MCP Interfaces

MCP is for external agents such as Claude Code, Claude Desktop, Antigravity,
Codex/Cursor integrations, or any MCP-capable client.

### 3.1 Existing Tools To Keep

- `curator_check_workspace`
- `curator_query`
- `search_curator`
- `fetch_document_section`
- `curator_get_node`
- `curator_traverse_evidence`
- `curator_update_node`
- `promote_exhibition`

### 3.2 New Or Upgraded Tools

Proposed:

- `curator_plan_workspace(workspace_path)`
- `curator_explore_workspace(question, workspace_path, limit)`
- `curator_list_insight_candidates(workspace_path, status)`
- `curator_get_prompt_trace(trace_id)`
- `curator_validate_curate_spec(workspace_path)`

### 3.3 External Agent Session Rule

External agents should:

1. call `curator_check_workspace`;
2. inspect active `curate.yml` summary and Exhibition state;
3. use `curator_query` for synthesis;
4. use `search_curator` only for raw hits;
5. use `curator_update_node` or promotion tools for feedback.

## 4. Plugin JSON Interfaces

The plugin should use hidden backend commands:

```bash
wiki plugin curate plan --workspace PATH --json
wiki plugin query --workspace PATH --mode auto --json
wiki plugin prompt trace --trace-id ID --json
wiki plugin insight list --workspace PATH --json
wiki plugin insight promote --candidate-id ID --json
```

These commands are not the human-facing CLI surface. They are local backend API
commands for the Obsidian plugin.

## 5. Runtime Snapshots

Backend-owned snapshots under `.curator/runtime/` should include:

- `status.json`;
- `sources.json`;
- `jobs.json`;
- future `curation.json`;
- future `prompt_traces_recent.json` if useful.

The plugin reads snapshots but does not write them.

## 6. Trace Payload

Every curation/query/explore response should include a trace object:

```json
{
  "trace_id": "TRC-...",
  "workspace_path": "...",
  "curate_spec_hash": "...",
  "route": "local|global|explore|exhibition",
  "route_reason": "...",
  "exhibition_id": "EXH-...",
  "sources": [],
  "source_spans": [],
  "concepts": [],
  "entities": [],
  "community_reports": [],
  "prompt_runs": [],
  "insight_candidates": [],
  "latency_ms": 0,
  "warnings": []
}
```

## 7. Plugin UX Requirements

The chat trace panel should show:

- active workspace;
- `curate.yml` spec hash;
- route decision;
- active Exhibition;
- source spans;
- concept/entity/community path;
- prompt id/version;
- prompt validation state;
- insight candidates;
- promotion/backprop actions when available.

## 8. Compatibility

Existing commands should keep working while v0.3.1 behavior is introduced:

- `wiki query` remains usable.
- `curator_query` remains the main synthesis MCP tool.
- old clients that do not understand prompt traces can ignore new fields.
- plugin/backend version mismatch should surface clear warnings.

## 9. Acceptance Criteria

Interface design is accepted when:

- external MCP and local plugin JSON are clearly separated;
- both call shared backend services;
- trace payload shape is stable;
- prompt trace can be inspected;
- `curate.yml` validation is exposed;
- plugin never directly mutates `.curator/state.sqlite`.


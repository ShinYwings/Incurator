# v0.3.2 Dashboard Click-To-Use — Trace and Insight Queue

Date: 2026-06-04
Status: Queued plan artifact. No active spec/code changes yet.

## 0. Baseline

The backend already has:

- `INS-` insight candidates
- `PTR-` prompt traces
- `QTR-` query trace ids returned by query results
- `curator_promote_insight`
- `curator_propose_correction`
- hidden plugin JSON commands for prompt trace, insight list, and insight promote

The plugin already has:

- `IncuratorClient.getPromptTrace`
- `listInsightCandidates`
- `promoteInsight`
- Sources & Trace panel
- Dashboard tabs for overview/jobs/sources/persona

The current gap is that `QTR-` is not durably queryable as a first-class trace
object. It is present in query responses and `prompt_runs.query_trace_id`, but
dashboard click-to-use needs list/show APIs.

## 1. User Workflows

### 1.1 Query Trace Drilldown

User opens Dashboard -> Trace tab -> selects a recent `QTR-`.

The detail view shows:

- route
- route reason
- warnings
- expansion/ranking/rerank degraded state
- source spans
- community reports
- synthesis nodes
- memory paths
- prompt trace ids
- insight candidate ids
- retrieval stage summary

IDs are clickable. `PTR-` opens prompt trace detail. `INS-` opens insight detail.
Projection/node links open Obsidian notes when the projection exists.

### 1.2 Insight Review

User opens Dashboard -> Insights tab and filters:

- pending
- needs_review
- promoted
- rejected

The detail view shows:

- classification
- statement
- evidence
- affected nodes
- confidence
- source event
- prompt run id
- creation/update timestamps

The user can promote, reject, or start a correction proposal.

### 1.3 Promotion

Promotion is explicit and confirmed.

Backend writes only to `02_Wiki/`, marks the candidate promoted, returns the
promoted path, and dashboard refreshes the row. No generated node, source note,
resource, or archive is edited directly.

### 1.4 Correction

Correction starts from a trace, insight, or generated artifact.

Dashboard collects:

- node id
- correction text
- optional previous text
- workspace path

Backend runs the existing correction classifier and returns the recommended
action. Dashboard displays the classification and any created insight candidate.
It never directly overwrites generated nodes.

## 2. Backend JSON Commands

Keep existing:

```text
wiki plugin prompt trace --trace-id PTR-... --json
wiki plugin insight list --workspace-path PATH --status pending --json
wiki plugin insight promote --insight-id INS-... --workspace-path PATH --json
```

Add in v0.3.2:

```text
wiki plugin trace list --workspace-path PATH --limit 50 --json
wiki plugin trace show --trace-id QTR-... --workspace-path PATH --json
wiki plugin insight show --insight-id INS-... --workspace-path PATH --json
wiki plugin insight reject --insight-id INS-... --workspace-path PATH --reason TEXT --json
wiki plugin correction propose --node-id ID --correction TEXT --previous TEXT --workspace-path PATH --json
```

## 3. Durable Query Trace Schema

Recommended addition:

```sql
CREATE TABLE IF NOT EXISTS query_traces (
    trace_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    question_hash TEXT NOT NULL,
    route TEXT NOT NULL,
    route_reason TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    community_report_ids TEXT NOT NULL DEFAULT '[]',
    synthesis_node_ids TEXT NOT NULL DEFAULT '[]',
    memory_path_ids TEXT NOT NULL DEFAULT '[]',
    prompt_trace_ids TEXT NOT NULL DEFAULT '[]',
    insight_candidate_ids TEXT NOT NULL DEFAULT '[]',
    retrieval_trace_json TEXT NOT NULL DEFAULT '{}',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    latency_ms INTEGER,
    created_at TEXT NOT NULL
);
```

`prompt_runs.query_trace_id` remains the join key. The trace stores ids and
hashes, not raw prompt bodies.

## 4. Payload Shapes

```ts
type TraceListResult = {
  ok: boolean;
  traces: QueryTraceSummary[];
  error?: string;
};

type QueryTraceDetail = {
  ok: boolean;
  traceId: string;
  workspaceId: string;
  route: "local" | "global" | "explore" | "source-section";
  routeReason: string;
  sourceSpanIds: string[];
  communityReportIds: string[];
  synthesisNodeIds: string[];
  memoryPathIds: string[];
  promptTraceIds: string[];
  insightCandidateIds: string[];
  retrievalTrace?: {
    expansions?: unknown[];
    ftsCandidates?: unknown[];
    vectorCandidates?: unknown[];
    rrf?: unknown[];
    rerank?: unknown[];
    degraded?: string[];
  };
  warnings: string[];
  latencyMs?: number;
  createdAt: string;
};
```

`InsightDetail` extends the existing candidate payload with:

- `evidence`
- `sourceEventId`
- `promptRunId`
- `createdAt`
- `updatedAt`

## 5. UI States

- Trace tab loading: compact table skeleton or single loading row.
- Trace tab empty: "No traces yet".
- Insights tab loading: compact table skeleton or single loading row.
- Insights tab empty: "No pending insights".
- Degraded trace: show partial trace when only `prompt_runs` exist for a `QTR-`.
- Error: inline error plus Refresh action.
- Mutation pending: disable action button and show running state.
- Promotion success: show promoted path and move row to promoted.
- Correction result: show classification, recommended action, candidate id if
  created, and review-required badge.

## 6. Safety Constraints

- Dashboard never writes `.curator/state.sqlite` directly.
- Dashboard never edits `.curator/Collections`, `03_Notes`, `04_Resources`, or
  `06_Archives` directly.
- Runtime snapshots remain backend-owned read models.
- Same-device dashboard actions use hidden `wiki plugin ... --json` commands, not MCP.
- Promotion requires explicit confirmation and writes only to `02_Wiki/`.
- Correction uses backend classification; no direct generated-node overwrite.
- Prompt trace UI does not expose raw prompt input/output by default in v0.3.2.

## 7. Tests

Backend:

- `test_v032_query_trace_persistence.py`
- `test_v032_plugin_trace_commands.py`
- `test_v032_plugin_insight_show_reject.py`
- `test_v032_correction_propose_plugin.py`

Plugin:

- `incuratorClientV032.test.ts`
- `incuratorDashboardModal.test.ts`
- source-string guard that dashboard uses client/backend commands only
- promotion confirmation test
- disabled mutation-state test

Testbed:

```bash
wiki testbed init <active_scenario> --force
VAULT_ROOT=testbed wiki build --wait
VAULT_ROOT=testbed wiki query --route explore "Find a derived insight worth reviewing."
VAULT_ROOT=testbed wiki plugin trace list --workspace-path testbed --json
VAULT_ROOT=testbed wiki plugin insight list --workspace-path testbed --json
VAULT_ROOT=testbed wiki plugin insight promote --insight-id INS-... --workspace-path testbed --json
VAULT_ROOT=testbed wiki lint
VAULT_ROOT=testbed wiki sync
```

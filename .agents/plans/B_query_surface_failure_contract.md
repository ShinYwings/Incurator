# Domain Analysis B — CLI, MCP, And Plugin Failure Contract

Date: 2026-07-30

## Design constraints from the current codebase

- `_run_query_repl()` returns `None`; it prints a `QueryResult.error` but cannot
  tell `commands/core.py::query` to exit non-zero.
- `CliQueryCallbacks.on_complete()` prints only a newline on the current
  non-streaming orchestrator path, so success can be silent.
- Plugin API and MCP each build a client, run the same orchestrator, catch broad
  exceptions, inspect result success, load QTR metadata, resolve source paths,
  and serialize a query payload independently.
- Both adapters discard QTR/PTR/provenance on a normal failed result.
- `wiki plugin query` prints returned `{ok:false}` payloads but exits 0.
- `plugin/main.ts::runBackendJsonCommand()` intentionally parses stdout JSON
  even when the child exits non-zero.
- `CuratorQueryResult` and its normalizer already support every required
  existing trace field.
- The MCP tool-result compactor preserves `error`, `trace`, and QTR but drops
  top-level prompt trace ids and warnings; the trace panel does not render the
  failure reason.

## Docs/spec invariants

- `wiki query` and `curator_query` are sessionless and return answer/trace without
  writing a vault file.
- The hidden plugin JSON namespace is the same-device backend boundary; the MCP
  server is the external-agent boundary.
- A failed synthesized answer preserves retrieval provenance and its failed
  synthesis action.
- Plugin-visible MCP output must retain parseable error and trace information.
- Workspace-policy failures occur before provider startup and remain distinct.

## Alternatives and trade-offs

### Add a new public problem-details object

Rejected for v0.37.1. It would be an additive public contract change, require a
minor release, and duplicate existing query/trace fields.

### Keep MCP and plugin query implementations independent

Rejected. Their duplicated control flow caused the exact trace-loss divergence
being fixed and makes parity tests compare copies rather than one contract.

### Delegate MCP to the backend-local plugin API

Selected with explicit MCP language defaults. `plugin_api` stays dependency-free
from MCP; MCP becomes a thin transport adapter. No existing successful field is
removed, and the result is an additive superset of the previous MCP payload.

### Raise an MCP protocol error for provider failure

Rejected for this patch. MCP's current public tool contract is a domain
`{ok:false}` result consumed by existing clients. Returning its structured trace
lets an agent inspect/retry; changing FastMCP protocol-error behavior is a
separate contract decision.

## Final decision

- One serializer emits success and failure from the existing query result.
- MCP `curator_query` calls the same backend-local query service with explicit
  `final_output_language="English"`.
- Failure payloads keep answer empty plus QTR/PTR/provenance and a bounded
  actionable error.
- CLI prints a non-streamed answer. `_run_query_repl` returns `had_failure`;
  the command exits 1 after provider cleanup if true.
- Hidden plugin query prints exactly one JSON object and exits 1 when `ok=false`.
- Plugin normalization remains unchanged but gains a failure fixture.
- MCP display compaction keeps `prompt_trace_ids` and warnings, and the Sources
  & Trace panel renders the failure reason beside retained trace data.

## Surface contract

| Surface | Success | Expected provider/validation failure |
|---|---|---|
| CLI | answer printed, exit 0 | concise error + QTR/PTR, no traceback, exit 1 |
| MCP | existing answer/trace payload | `ok:false` with existing trace/provenance fields |
| Hidden plugin CLI | one JSON object, exit 0 | one parseable JSON object, exit 1 |
| Plugin UI | normal answer/trace | visible error plus navigable QTR/PTR trace |

## Implementation pseudocode

```python
def query(...):
    result = run_orchestrator(...)
    return serialize_query_result(result, ...)

def plugin_query(...):
    payload = plugin_api.curator_query(...)
    print_json(payload)
    if not payload["ok"]:
        raise typer.Exit(1)

had_failure = run_query_repl(...)
if had_failure:
    raise typer.Exit(1)
```

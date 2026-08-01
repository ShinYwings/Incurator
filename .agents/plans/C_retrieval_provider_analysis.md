# Domain Analysis C — Retrieval, Provider, Prompt, And Process Boundaries

Date: 2026-07-30
Status: ACTIVE — input to regression-audit P7 and P8.
Confirmed findings: F08–F13, F19–F22.

## 1. Design Constraints And Invariants

- Hybrid search must explicitly trace lexical/vector/reranker degradation.
- Provider result cardinality must match request cardinality; partial zip is not
  success.
- Quick Query and Sidechat must honor the same selected provider/model while
  preserving their different tool policies.
- Every in-flight request has an independently cancelable lifetime.
- A caller-owned request must not replace the sidebar foreground pointer, and
  an already-aborted request must not launch any provider transport.
- Provider-specific error mapping must preserve cancellation as `AbortError`.
- MCP tool exposure may sanitize model-facing identifiers, but dispatch must use
  the original server and tool names.
- Shutdown/timeout must settle every pending Promise exactly once.
- Prompt traces must identify the provider/model that actually produced output.
- Backend subprocesses must be bounded without truncating legitimate long jobs.

## 2. Confirmed Failure Modes

- Query-embedding exceptions silently become empty vector lists while the trace
  still claims vectors are available.
- One shared/cleared abort controller breaks CLI cancellation and overlapping
  request control.
- A caller-owned Quick Query can still become the global foreground request,
  causing sidebar Stop/session actions to cancel the wrong surface.
- Cancellation during asynchronous context preparation can reach the provider
  launch path with an already-aborted signal; Ollama rewrites aborts as
  connectivity errors.
- Non-streaming CLI drops the per-call model and GUI PATH augmentation.
- MCP name sanitization is lossy and colliding.
- MCP shutdown may clear pending requests without rejecting them.
- MCP stdout is not generation-guarded, so late bytes from an exited child can
  poison the replacement generation's shared newline-delimited JSON buffer.
- Plugin backend commands have no timeout or output cap.
- Reranker and embedding short responses silently truncate work.
- Failover prompt traces retain the failed primary provider attribution.
- Prompt version lookup sorts `v10` below `v9`.

## 3. Alternatives And Trade-Offs

### Global catch-and-fallback

Minimal code, but recreates the current problem: failures look like successful
lower-quality output and traces lie.

### Generic task manager abstraction

Could unify all provider/MCP/process lifetimes, but is excessive for the current
bounded set of defects.

### Small typed outcomes and request-local handles

Return explicit stage status from retrieval helpers; use one local abort/process
handle per request; maintain explicit MCP exposed-name maps; settle pending
requests in one shutdown function.

## 4. Final Decision

- `_vector_list` returns data plus a failure marker; the caller records
  `fallback_mode=lex` and a stable `vector_failed` warning, including in
  vec-only mode. Vec-only mode does not synthesize lexical candidates.
- Validate embedding/reranker lengths and finite numeric values before
  storing/ranking. Reject an invalid embedding batch without partial writes.
- Replace the single abort slot with request-owned handles and an explicit
  surface cancellation API; a shared slot may remain only as a pointer to the
  foreground request, never as the source of truth. Requests with an explicit
  owner signal do not replace the legacy sidebar foreground pointer.
- Reject already-aborted provider work before and after asynchronous launch
  preparation, and preserve `AbortError` through provider-specific mapping.
- Pass model and augmented environment into every CLI path.
- Build a bijective exposed-tool-name map; never reconstruct original names by
  splitting sanitized text.
- Reject every pending MCP request before clearing state and wait for exit or a
  bounded forced-kill completion. Guard stdout by process generation and reset
  the protocol buffer when a generation starts.
- Add command-class timeout/output policies to the plugin backend runner.
- Finalize prompt trace provider/model after successful failover.
- Parse `v<integer>(.<integer>)*` prompt versions into numeric tuples and reject
  malformed versions at registration; use the numeric key for latest lookup
  and registry listing.

## 5. Pseudocode

```text
vector_list(query):
    try:
        vectors = embed(query)
        validate_exact_count(vectors, 1)
        return VectorOutcome(ok=True, hits=search(vectors[0]))
    except ExpectedProviderError as error:
        return VectorOutcome(ok=False, warning=stable_code(error))
```

```text
exposed_tools = {}
for tool in raw_tools:
    exposed = collision_free_identifier(tool.server_name, tool.name)
    exposed_tools[exposed] = (tool.server_name, tool.name)

dispatch(call):
    server, tool = exposed_tools[call.name]
    return mcp.call_tool(server, tool, call.args)
```

```text
shutdown():
    pending = take_all_pending()
    for request in pending:
        request.reject(ShutdownError)
    terminate_process_with_deadline()
    clear_runtime_state()
```

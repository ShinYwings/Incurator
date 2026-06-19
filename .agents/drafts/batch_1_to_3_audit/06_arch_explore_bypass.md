# Architectural Code Review: Explore Route Bypassing ContextService

## Target
`backend/src/curator/retrieval/orchestrator.py` -> `run()`

## Vulnerability Description
The `QueryOrchestrator` explicitly bypasses the newly introduced `ContextService` when the route is `"explore"`. This directly violates the Plan F Strict Quality Condition.

### Code Reference
```python
        if route != "explore":
            context_pack = ContextService(self.paths, self.client).context_fetch(request)
            # ...
            return result

        # --- Explore Branch ---
        trace_id = f"QTR-{uuid.uuid4().hex[:8]}"
        pack = evidence_mod.build_evidence(self.paths, request, route, policy=policy)
        # ... bypasses ContextService, calls old build_evidence
```

### Deep Analysis
1. **Contract Violation:** Plan F states: "Every route applies the same workspace/KRS policy, scope, authority, freshness, snapshot, and budget enforcement." By bypassing `ContextService`, the `explore` route does not generate a `PACK-*` ID, does not enforce `limit_tokens` via `_apply_budget`, does not create `CTXA-*` child actions, and does not freeze a `SNAP-*` snapshot.
2. **Dual Trace Logic:** This forces the system to maintain two parallel tracing mechanisms. The `explore` branch manually generates a `QTR-*` ID and builds its own `retrieval_trace` using `_build_retrieval_trace()`, fragmenting the database schema and making cross-client parity impossible.
3. **Future Block:** Plan F P8 (Plan-A Route Admission) cannot be completed if the `explore` route operates completely outside the service boundary.

### Recommended Rewrite
The `explore` route MUST route through `ContextService.context_fetch` to obtain its initial grounding evidence, exactly like the local and global routes. The unique behavior of "explore" (generating follow-up questions and insight candidates) belongs in the synthesis phase (`_run_explore`), which should consume the normalized `ContextService` pack, not bypass it.

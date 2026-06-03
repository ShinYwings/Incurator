# 2026-06 Chunking Edge Cases and UI Errors Plan

## Goal
Improve L2/L3 pipeline resilience against excessively large spans/units (edge cases) and expose error states clearly in the Obsidian dashboard UI. Support asynchronous daemon-based queue execution for `wiki build` so the queue automatically processes without needing MCP active.

## Proposed Changes

### 1. Robust Chunking (Edge Cases)
- **Problem**: In `knowledge_units.py` and `graph_index.py`, if a *single* `span` or `unit` exceeds `optimal_chunk_chars`, it gets batched alone and still causes a Token Limit Exceeded error.
- **Solution**: 
  - If a single span's text exceeds `max_chars`, split it using `_chunk_text` from `ingest_raw.py` before batching. Keep the same `span_id` so DB references remain valid.
  - If a single unit's statement exceeds `max_chars`, truncate it to `max_chars` (as units are synthesized claims, they shouldn't be massive, but defensive truncation prevents crashes).

### 2. UI Error Visibility
- **Problem**: The UI shows an `Error` badge for failed sources but doesn't display the actual error message (`layer_error` from DB).
- **Solution**: 
  - Update `incuratorDashboardModal.ts` in the `renderSources` table. If `src.layer_error` exists, append a small error text block beneath the source path.

### 3. Asynchronous Queue Daemon
- **Problem**: Clicking "Build" in the dashboard queues jobs but doesn't run them unless MCP is active. 
- **Solution**: 
  - In `cli.py` `wiki build`: If `not wait`, enqueue jobs and then spawn a detached subprocess (`wiki jobs run`) so the jobs begin processing automatically in the background without blocking the CLI or Obsidian.

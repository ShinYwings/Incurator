# RELAY — v0.71.0 in flight

**Branch**: `release/v0.71.0` · **PR**: #187 (OPEN)

## Goal

Phase B2 — retention. Cap the LLM call log (`prompt_runs`) without ever deleting
a record an artifact still points at, and prune plugin sessions by age.

## Progress

- `wiki gc plan` / `wiki gc run`, `gc.prompt_runs_keep`, session retention: DONE
- The code-review skill was run on #187 and found six issues; all fixed.
  One was a fleet-wide silent data-loss path (`graph_batch_results.trace_id` —
  a prompt-run reference under a different column name that the completeness
  test was structurally incapable of catching).
- Retrospective reviews of v0.62.0–v0.71.0 found five more; all fixed here:
  sign-out never reached the encrypted store, the mid-stream quota kill fired on
  prose, a throwing snapshot wedged plugin persistence, per-source L4 status
  counted reports synthesis never cited, and a cleared `.cache/` overwrote an
  accurate ledger with "Last curated: never".
- Re-review of the post-review commits: running now.

## Critical context

- **Code review before CI is now a mandatory workflow step** (CLAUDE.md step 8,
  user directive 2026-08-24). It had been skipped for sixteen releases.
- The full backend suite caught a regression `734e420` introduced and I had not
  re-run pytest after: `is_knowledge_question` joined the derivation trace block
  without updating the exact-equality assertion that pins that block's shape.
  **Run the full suite before the PR, not just the touched files.**
- One LOW finding is recorded, not fixed: the provider key transits as CLI argv.
  Fixing it means threading stdin through `runBackendCommand`, the spawn every
  backend call shares. It is in `USER_REPORT.md` as its own item.

## Immediate next action

Land the re-review findings, merge #187, then take the next `ROADMAP.md` item —
Phase B2's remaining synced-table targets, then Phase D.

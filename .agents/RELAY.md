# Active Relay State

**STATUS: Planning — XC-1 error-handling narrowing plan drafted, AWAITING USER APPROVAL. No code yet.**

**Current branch**: `master` (no feature branch created until plan approved)

**Last refreshed**: 2026-06-28 by Claude Code.

---

## Goal

Phase C of the System Stability Overhaul: XC-1 broad-`except` narrowing,
**slice 1** — the backend data-pipeline core (`config.py`, `parsers/pdf.py`,
`llm.py` handlers only, `ingest_raw.py`, `ingest_worker.py`,
`pipeline/compile.py`; ~51 of 270 backend broad-excepts). Classify each into
{KEEP, NARROW, SURFACE, DELETE} and resolve, surfacing masked failures without
regressing the pipeline's intentional fault-tolerance. Target **v0.27.5** (Patch
— internal error-handling only; no schema/contract change, so spec titles stay on
the 0.27 line).

## Plan Reference (DRAFT — needs approval before coding)

- Master plan: `.agents/plans/02_error_handling_narrowing.md`
- Domain analysis: `.agents/plans/A_exception_taxonomy.md`
- Arena: `.agents/plans/xc1_error_handling_arena/` (00_problem, 01_proposal, 02_critique)

## Progress Status

- v0.27.4 (G17 S3) merged via PR #63; repo synced; was IDLE.
- Authored the XC-1 slice-1 Arena plan + Domain Analysis + Master Plan.
- Updated ROADMAP active-plan note.
- **STOPPED for user approval per Universal Strict Workflow Step 4.**

## Immediate Next Action

WAIT for user approval of `02_error_handling_narrowing.md`. On approval:
create branch `fix/error-handling-pipeline`, write the evidence ledger
`02_roadmap_evidence.md` (P0 inventory), then execute P1→P5 (TDD per site).

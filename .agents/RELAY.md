# Active Relay State

**STATUS: Planning — DB-2 db.py decomposition plan drafted, AWAITING USER APPROVAL. No code yet.**

**Current branch**: `master` (feature branch created only after approval)

**Last refreshed**: 2026-06-28 by Claude Code.

---

## Goal

System Stability Overhaul Phase C, S2 god-file decomposition **DB-2**:
convert `backend/src/curator/db.py` (4759 LOC) into a `db/` package with a
re-export facade — **zero caller changes** (all callers use `db.<name>` module
access; verified zero name-imports) and **zero behavior change** (verbatim moves).
Slice 1 extracts `schema.py` + `jobs.py`; the rest moves to a holding
`db/_entities.py` re-exported by the facade, carved per-entity in follow-ups.
Target **v0.27.7** (Patch — internal refactor).

## Plan Reference (DRAFT — needs approval before coding)
- Master plan: `.agents/plans/04_db_decomposition.md`
- Domain analysis: `.agents/plans/C_db_package_layout.md`
- Arena: `.agents/plans/db2_decomp_arena/` (00_problem, 01_proposal, 02_critique)

## Progress Status
- v0.27.6 (Robustness Slice 2) merged via PR #65; repo synced; was IDLE.
- Authored the DB-2 slice-1 Arena plan + domain analysis + master plan.
- **STOPPED for user approval (Universal Strict Workflow Step 4).**

## Immediate Next Action
WAIT for approval of `04_db_decomposition.md`. On approval: branch
`fix/db-decomposition`, write `04_roadmap_evidence.md`, then P0 (API snapshot
test + baseline) → P1 (package + schema.py + _entities.py + facade) → P2
(jobs.py) → P3 (verify + docs + release). Full pytest + mypy after each move.

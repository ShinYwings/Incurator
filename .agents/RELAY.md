# Cross-Agent Relay State

## Goal
Implement RAG Post-Stabilization Hardening (Roadmap Item 1) — re-scoped to the
**systemic group only** after grounding the audit against the live tree.

## Branch
`feature/rag-hardening` from `master`.

## Current State
State 3 (Plan Exists, awaiting approval). Arena debate concluded; master plan
authored. **No code written yet** — waiting on user approval (Universal Strict
Workflow Step 4).

## Critical Context — audit was stale
The `batch_1_to_3_audit` drafts were written against a pre-stabilization tree.
Grounding (2026-06-20) proved **6 of 10 findings are already shipped** and pinned
by regression tests, so they are OUT OF SCOPE:
- 04 (orphaned_support), 05 (budget_exhausted), 08 (CJK token est),
  09 (rank order preserved), 10 (expansion state) — FIXED.
- 07 (trace mutation) — intentional & tested behavior, not a bug.
Evidence table: `.agents/plans/rag_systemic_hardening_arena/00_problem.md`.

## Plan Reference
- Master plan: `.agents/plans/01_rag_systemic_hardening.md`
- Evidence ledger: `.agents/plans/01_rag_systemic_hardening_evidence.md`
- Arena debate: `.agents/plans/rag_systemic_hardening_arena/`
- Scope: 06 (explore→ContextService) → 03 (soft-rebase + healing) → 02 (soft-links
  + giant-component quarantine) → 01 (atlas promotion + noise injection).

## Immediate Next Action
**HUMAN**: review and approve `.agents/plans/01_rag_systemic_hardening.md`.
On approval, EXECUTORS start at **P0 (Research & Measured Baseline)** — measure
epoch granularity (gates P-03a), baseline explore trace, graph density, atlas
contract — then P1 docs-first spec work. Do NOT skip to coding before P0/P1.

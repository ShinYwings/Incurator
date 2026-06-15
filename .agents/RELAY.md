# Cross-Agent Relay State

## Status: IDLE — Plan A shipped, awaiting PR merge

**Branch:** `feature/plan-a-rag-retrieval-provenance`

Plan A (RAG Retrieval Provenance, v0.10.0) is complete and staged for PR.

## Summary of Work Done
- P2: RTR-* retrieval execution ID, EvidencePack/EvidenceItem new fields
- P3: CurationPolicy forwarding (F3 fixed), bounded global route (F4 fixed), explicit omission marker (F5 fixed)
- P4: StructuredLocator resolution on source-span evidence items
- P5: Plan-F handoff contract in fetch_context (RTR-* + locator data)
- P7: Sequential roles, full CI, version bump 0.9.0→0.10.0, CHANGELOG, Failure Atlas F03/F04/F05 retired

## Immediate Next Action
For the Brain (PM): Review PR #31 when updated.
For the Executor: Read `.agents/drafts/diff_viewer_plugin.md` and create a `PLAN_TEMPLATE.md` in `.agents/plans/` for the Diff Viewer Overhaul milestone.

### Update (2026-06-16, Claude Code) — PR #31 review fixes pushed
Addressed the 5 PR #31 review findings on the same branch before merge (plan-first;
plan `A2_plan_a_review_fixes.md` approved, implemented via TDD, then deleted):
- F3 (§28.1) now **behaviorally** enforced — glob source-scope filter via
  `CurationPolicy.allows_source`, centralized in `_apply_policy_scope` on every route.
  The premature v0.10.0 "retired" status was corrected, then re-retired with a
  behavioral oracle.
- `evidence_block` budget-safe omission marker (§28.3); `promoted_wiki` locator
  kind (§29.2); `candidate_count = selected + omitted` (§30.2).
- Spec §28.1 + SCHEMA §22 reconciled to the real glob policy surface (no `source_ids`).
- Full CI green: 894 passed, 5 xfailed (F6/F8/F9/F11/F12 = Plan C/F scope).
Diff Viewer Overhaul (ROADMAP 4.5) remains the next milestone and is untouched.

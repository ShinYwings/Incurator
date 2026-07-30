# RELAY — ACTIVE

## Goal

Continue the System Stability Overhaul as three related, independently
reviewable workstreams: composite-primary-key tombstones, query-provider
failure UX, and authored-wikilink architecture validation.

## Plan Reference

- Umbrella: `.agents/plans/01_system_stability_overhaul.md`
- Evidence: `.agents/plans/01_roadmap_evidence.md`
- Current branch: `release/v0.37.0`

## Analysis & Reasoning

- All three workstreams belong to the stability program, but they cross
  different correctness boundaries and must not become one mega-PR.
- The ordered delivery chain is tombstone integrity → provider error boundary →
  wikilink topology validation.
- Composite tombstones are first because the current importer records a
  tombstone and increments deletion stats without deleting a composite-key row.
  The transport key must also avoid replica-local `sources.id` values.

## Progress Status

- Phase A diagnosis is complete and consolidated.
- Current code/schema/test paths for all three workstreams have been rechecked.
- Stale `.agents` status labels have been reconciled with the current Git state.
- The v0.37.0 Arena plan and evidence ledger are complete, and the user approved
  the schema/wire contract. Docs-first/TDD implementation is underway.

## Critical Context / Blockers

- The approved wire contract bumps the schema to v13 and fails closed on
  unsupported legacy composite tombstones.
- `source_pages` and `source_pdf_pages` use replica-local `source_id` in their
  primary keys, so their transport identity must use `sources.sync_key`.
- Failure Atlas/test F9 means authored wikilink topology, while
  `SYSTEM_BEHAVIOR.md` §27 reuses F9 for broad-span grounding. The wikilink slice
  must resolve that contract collision before changing code.
- Provider-error UX and wikilink validation remain out of this release.

## Immediate Next Action

Finish the v0.37.0 EN/KR spec and guide updates, then write the failing
composite tombstone convergence tests before application logic.

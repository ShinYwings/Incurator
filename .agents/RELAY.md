# RELAY — v0.37.0 RELEASE HANDOFF

## Goal

Continue the System Stability Overhaul through independently reviewable
integrity releases. Composite-primary-key tombstones are complete in v0.37.0;
query-provider failure UX is the next workstream after merge.

## Plan Reference

- Umbrella: `.agents/plans/01_system_stability_overhaul.md`
- Evidence: `.agents/plans/01_roadmap_evidence.md`
- Current branch: `release/v0.37.0`

## Analysis & Reasoning

- Schema v13 uses a closed canonical-JSON key registry for all six synchronized
  composite-primary-key tables.
- Source-scoped transport keys use `sources.sync_key`, never a replica-local
  numeric id.
- Tombstones win equal revisions, strictly newer mutable rows may supersede
  them, immutable rows may not, and malformed/legacy composite tokens fail
  closed.
- Source deletion and local composite-row lifecycle paths now share
  transactional helpers instead of duplicating partial cleanup.

## Progress Status

- v0.37.0 implementation, EN/KR docs, TDD, code review, version sync, changelog,
  and testbed validation are complete.
- Code review found and fixed first-import dry-run source-key resolution; its
  preview counts now match the real pass without writes.
- Final gates: backend 1,303 passed; Ruff and Mypy passed; plugin 721 passed;
  production build passed; ResNet testbed autosync became quiescent and lint
  scored 100/100.
- The release branch is ready for PR review and merge.

## Critical Context / Blockers

- v12 and v13 peer snapshots do not partially interoperate. Every peer must
  upgrade and re-export before cross-device sync resumes.
- Query-provider failure UX and authored-wikilink validation remain separate
  releases; neither is included in v0.37.0.
- The wikilink slice must reconcile the conflicting Failure Atlas F9 meanings
  before changing topology code.

## Immediate Next Action

Review and merge the v0.37.0 PR from `release/v0.37.0`. After merge, update
local `master` and begin the query-provider failure UX plan from that clean
base.

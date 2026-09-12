# RELAY

**Branch:** `master`

## Goal

Continue the ROADMAP active queue from B1/B2 retention; the cache correctness
prerequisite shipped as v0.82.6 / PR #207 on 2026-09-12.

## Plan Reference

No implementation plan active. Unresolved prompt-lifetime and session-writer
findings/proposals remain in `.agents/plans/retention_followup_arena/`.
Implemented cache plan/evidence are in Git history, removed from active files.

## Analysis & Reasoning

Cache selection now preserves retained data and unknown files/schema, inspects
only a private DB copy, and rejects observed stale candidates before deletion.
Opening a WAL DB even mode=ro created sidecars; private-copy inspection fixes
that without altering originals. Final checks are not an atomic writer lease.

Next correctness issue: prompt runs commit before provider completion and before
artifact publication. A finite cap can delete a live producer's unreferenced run.
BEGIN IMMEDIATE alone merely postpones a publisher until after deletion. Need
an ownership/lifetime design across callers and peers, not a timing grace period.
Session pruning separately races Obsidian's writer and stale selected-message
state; design coordination before exposing Dashboard Run GC. Full replay and
thumbnails remain required. Tombstones have no fleet acknowledgement floor.

## Progress Status

- PR #207 merged; v0.82.6. Backend 2015 passed, 6 skipped, 4 xfailed; plugin
  Vitest 4.1.11 1286 passed, 3 skipped. Ruff, mypy, TypeScript, testbed gc preview
  and all GitHub CI passed.
- Actual `/code-review:code-review 207` failed expired Claude OAuth. User said
  "don't care claude code" and authorized proceeding with available agents.
  Three independent reviewers covered five lenses; no introduced findings ≥80.
  This was a recorded substitution, not a successful skill invocation.
- No production GC, migration, reindex or retention setting change. Production
  last_root remains `/Users/shin/shinywings/second_brain`.

## Critical Context/Blockers

Do not disable useful reclamation, truncate chats or expire history as a silent
stability trade. Product capability reductions need a concrete user decision.
Actual production data deletion/migration still needs authorization. Prompt-run
policy was delegated; session window remains user-selected. No new finite
job/query/compiler history windows have been selected.

## Immediate Next Action

Arena the prompt-run lifetime defect using retained proposals and exact producer
paths. Keep session writer/Dashboard and user-history policy as explicit subsequent
work. Cache release cleanup is complete when master bookkeeping is pushed and
merged branch/worktree pruning is verified.

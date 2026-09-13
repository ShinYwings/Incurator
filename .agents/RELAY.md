# RELAY

**Branch:** `fix/schema-open-guard`

## Goal

Continue the ROADMAP active queue from B1/B2 retention; the cache correctness
prerequisite shipped as v0.82.6 / PR #207 on 2026-09-12.

## Plan Reference

Active prerequisite plan: `.agents/plans/08_schema_open_guard.md`, v0.82.7.
Independent review accepted pre-setup refusal of newer/malformed schema stamps.
The prompt-lifetime Arena is underway at
`.agents/plans/prompt_lifetime_arena/00_problem.md`. Prior prompt-lifetime and
session-writer findings remain in `.agents/plans/retention_followup_arena/`.
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
Session pruning races Obsidian's writer and stale selected-message state.
User decided on 2026-09-13: "Protect saved chat links too; retain diagnostics
while those chats exist". Saved chats are retention owners alongside knowledge
records and stored query traces. Session save/delete/sync coordination is now
a prerequisite of this lifetime contract, not a later optional protection.
Full replay and thumbnails remain required. Tombstones have no fleet
acknowledgement floor.

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
- Independent producer/fleet/retention proposals and cross-critiques are saved
  in prompt_lifetime_arena. A two-device private reproduction proved both
  directions of GC tombstone import can leave live report references dangling.
  Latest Arena extension covers saved chat ownership, offline saving and
  recoverable session commits. No lifetime application code changed yet.
- v0.82.7 prerequisite implemented on fix/schema-open-guard: reject future or
  malformed schema stamps before application setup. Review found and fixed
  same-name trigger ambiguity. Final backend 2045 passed, 6 skipped, 4 xfailed;
  plugin 1286 passed, 3 skipped. Ruff/mypy/TypeScript/testbed status passed.
  D2 hash re-armed with demonstrated unchanged 141-object initialized schema;
  consumed holdout was not rerun. Remote CI/merge/cleanup next.

## Critical Context/Blockers

Do not disable useful reclamation, truncate chats or expire history as a silent
stability trade. Product capability reductions need a concrete user decision.
Actual production data deletion/migration still needs authorization. Prompt-run
policy was delegated; session window remains user-selected. No new finite
job/query/compiler history windows have been selected.

## Immediate Next Action

Finish saved-chat extension and synthesize the template-compliant prompt
lifetime plan. Session writer correctness belongs in this design; Dashboard
controls and new history-window policy remain subsequent.
First implement and ship the independent v0.82.7 schema-open guard prerequisite
while the saved-session/handoff design closes in parallel. It changes no schema
version and performs no production migration.
Cache release cleanup is complete: master bookkeeping pushed, merged branch
pruned locally/remotely, sole worktree clean before new Arena bookkeeping.

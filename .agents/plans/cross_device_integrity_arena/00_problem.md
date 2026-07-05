# Cross-Device Integrity Boundary Briefing
Date: 2026-07-05

## User Intent

Extend the open v0.32.1 hotfix instead of deferring the cross-device audit to
v0.33.0. The user permits concurrent reads and concurrent work on different
source files, but does not edit the same source file on both devices at once.

The storage boundary is strict:

- device-dependent and volatile state belongs only under the Incurator
  repository `.cache/`;
- portable/shared state belongs under the vault `.curator/`;
- no legacy path command or permanent compatibility fallback may remain.

## Reproduced Failures

1. Distinct sources created on two devices can both receive numeric `sources.id
   = 1`; importing one snapshot overwrites the other source and its layer counts.
2. Source deletion hard-deletes rows without recording a sync tombstone, so the
   peer resurrects or retains the source.
3. `compiler_generations` has no revision column, so a stale `staged` row can
   overwrite an authoritative generation and make L2-L4 serving counts vanish.
4. JSONL import accepts any local SQLite table and arbitrary row columns if the
   table exists.
5. Machine-local DB/runtime/staging/PDF/CLI state is still written inside the
   vault.
6. Shared singleton files have backend write paths that can race independently
   of user source-file editing.
7. `wiki reset` deletes shared chat sessions.
8. Peer import identity is file mtime, so a replaced snapshot with the same
   mtime can be skipped.
9. Zotero profile merging preserves peer-only profiles but has no deletion
   tombstones.

## Release Constraint

The package/plugin release remains v0.32.1 by explicit user direction. The
SQLite transport schema may advance to v12 inside that release. v11 peer
snapshots are rejected rather than supported through a compatibility shim.


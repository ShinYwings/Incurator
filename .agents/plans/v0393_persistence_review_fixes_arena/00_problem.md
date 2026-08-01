# PR #104 Durable-State Review Follow-Up — Briefing

Date: 2026-08-01
Status: APPROVED SCOPE — user requested “fix them” after reviewing all findings.
Master-plan target: `.agents/plans/03_v0393_persistence_review_fixes.md`

## Problem

PR #104 is green but its review reproduced three gaps in the new durability
contract:

1. `save_config()` obtains a per-target lock but replaces the freshly read
   project mapping with a snapshot loaded before that lock. A peer-only key
   written after the snapshot disappears on the stale save.
2. Plugin session/profile queues serialize only this process. If a synced peer
   changes canonical JSON after the read but before replacement, the stale
   merge overwrites that newly arrived state.
3. Backend atomic replacement uses a `0600` `mkstemp()` file. Config callers do
   not pass a mode, so an existing `0644`/`0664` file becomes `0600`; secret
   files must remain explicitly `0600`.

## Locked Constraints

- Remain on `release/v0.39.3` and update draft PR #104.
- No schema, CLI/MCP contract, or version-line change.
- Preserve missing/corrupt/unreadable fail-closed behavior and temp cleanup.
- Preserve removal of machine-local keys from synced project config.
- Preserve session/profile tombstone and merge semantics.
- Use isolated fixtures only; do not read or mutate production `second_brain`
  or the active testbed.
- English contracts first, then Korean guide synchronization if user-visible
  recovery behavior changes.

## Required Proofs

- A stale full project-config save retains a peer-only key written after the
  snapshot, while machine-local keys remain absent from project YAML.
- Existing config mode `0664` survives success; new config uses normal
  umask-derived permissions; explicit secret mode remains `0600`; interrupted
  replacement preserves target bytes and mode.
- An adversarial adapter injects a peer session/profile update between initial
  read and commit; the final canonical JSON contains peer and local entries.
- Corrupt/unreadable canonical JSON still blocks saves without modification.

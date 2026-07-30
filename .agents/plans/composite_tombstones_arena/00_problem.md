# Composite-Primary-Key Tombstones — Briefing

Date: 2026-07-30 | Branch: `release/v0.37.0`

## Problem

Cross-device sync claims that tombstones delete canonical rows and defeat stale
updates. The current implementation cannot identify a composite-key row,
records the unsupported tombstone anyway, increments delete statistics, and can
later resurrect even scalar-key rows from a stale peer because upserts do not
consult tombstones.

## Required outcome

- A portable, deterministic, validated composite key representation.
- No replica-local `source_id` on the wire.
- Delete/update LWW convergence for scalar and composite keys.
- Production emission at real hard-delete sites.
- Fail-closed legacy/malformed behavior.
- Transactional, dry-run, two-device, and stale-third-peer tests.
- Docs, guides, schema version, release manifests, and changelog synchronized.

## Non-goals

- Query-provider failure UX.
- Authored-wikilink topology compilation.
- A general event-sourcing rewrite or delta-sync protocol.
- Changes to the authoritative/derived storage model.


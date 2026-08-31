# v0.78.0 Briefing — one file, two sources, differing only by Unicode form

## The report

ROADMAP E6, triaged from `USER_REPORT.md` 2026-08-23, confirmed against the live
vault 2026-08-31 and re-confirmed 2026-09-01.

## Measured, not assumed

Live vault, 50 registered sources:

- **18 of 50 relpaths (36%) are stored in NFD**, the form macOS hands back from
  `readdir`. Most tooling — and most text the user types — produces NFC.
- **One pair already collides.** `04_Resources/References/Camera Pose Estimation
  from Lines using Plücker Coordinates2015 - Přibyl et al. - .md` exists twice:
  `id=35` in NFC and `id=46` in NFD.
- **Both rows carry the SAME `content_hash`** (`16d1e9b33723…`) and both are
  `status='curated'`. So the file was ingested twice and its knowledge is split
  across two source ids.

## Why the existing dedup did not catch it

`sources.relpath` is `TEXT NOT NULL UNIQUE`; `content_hash` carries only a plain
index (`idx_sources_hash`). Registration looks up
`SELECT ... FROM sources WHERE relpath = ?` (`ingest_raw.py:2096`) and compares
hashes only to decide whether the file at THAT path changed.

So the "content-hash dedup" named in CLAUDE.md is change-detection on a known
path, not cross-path identity. Two byte-different strings that name the same file
are two sources, and nothing in the schema says otherwise.

## Where a fix has to reach

- 7 `WHERE relpath` sites across the backend.
- 33 sites computing a relpath from a `Path`.
- 14 modules mention `relpath` at all.

There is no chokepoint. That matters: v0.77.0's recurring defect was a fix landed
at one call site and silently absent at its sibling, four separate times. A
normalisation applied at 6 of 7 sites is the same bug wearing a new name, and the
7th site is the one that reintroduces the duplicate.

## The two halves, and their different authority

1. **Prevention** — normalise the identity so this stops happening. No user data
   is rewritten. Agent ships it.
2. **The pair that already exists** — merging two `sources` rows and everything
   downstream of them REWRITES the user's data. CLAUDE.md makes that a
   stop-and-ask.

   **Asked and approved, 2026-09-01.** The user said to merge it and ship both
   halves in this release.

## Constraints

- The DB is machine-local (`.cache/vaults/<hash>/state.sqlite`), but
  `db_sync.py` moves rows between devices, so `relpath` is part of a cross-device
  transport identity. Changing its stored form is a schema-adjacent change and
  needs the migration treated as one.
- `sources.sync_key` is the portable transport identity; `sources.id` is
  replica-local AUTOINCREMENT. A merge must respect both.
- No backward-compat shims (locked architecture decision). New runs use the new
  path directly.
- Nothing may be destroyed without a rehearsal that proves what it will do.

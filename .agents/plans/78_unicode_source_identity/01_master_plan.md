# v0.78.0 Master Implementation Plan — a file is one source, whatever form its name arrives in

## 1. Objective

The same file registers once, whichever Unicode normalisation form its path
arrives in, on every device. The one pair that already exists in the user's vault
is merged, with its downstream knowledge preserved.

## 2. Explicit Non-Goals

- Case-insensitive path matching. macOS filesystems are case-insensitive by
  default and that is a real second source of the same defect, but it is a
  different decision with a different blast radius (two files that differ only in
  case are legitimately distinct on Linux). Measure it, do not fix it here.
- Changing `sources.relpath`'s UNIQUE constraint or the `sync_key` transport
  identity.
- Any automatic merge. Normalisation is automatic; merging rewrites the user's
  data and stays explicit.

## 3. What the audit established

- 18 of 50 relpaths (36%) are stored NFD; one pair already collides, both rows
  `curated`, both carrying the same `content_hash`.
- Registration keys on `WHERE relpath = ?`, so hash equality is change-detection
  on a known path, never cross-path identity.
- **`db_sync` uses `relpath` as its cross-device reconciliation key**
  (`db_sync.py:1686`): when a peer's insert hits the UNIQUE constraint it looks
  the source up BY RELPATH to attach the peer's child rows to the local id. Two
  devices storing the same file in different forms therefore never collide, so
  the peer's rows attach to a NEW duplicate source instead of the existing one.
  This is a duplication *mechanism*, not merely a local annoyance, and it was not
  in the ROADMAP entry.
- 7 `WHERE relpath` sites, 33 sites deriving a relpath from a `Path`, 14 modules
  mentioning it. There is no chokepoint.

## 4. Locked Design Decisions

### D1. NFC, at the database boundary, guarded by a test

Normalise to **NFC** — the form nearly all tooling and all typed text produces;
NFD is the macOS `readdir` artefact.

Applied at every write to and comparison against `sources.relpath`. That is 7
comparison sites plus the inserts, and getting 6 of 7 right is the same bug in a
new place: v0.77.0 shipped four separate cases of a fix landing on one call site
and silently missing its sibling. So a **source-guard test** enumerates the
`WHERE relpath` sites and fails on one that binds an unnormalised value.

**Rejected:** normalising at the 33 path-derivation sites. More sites, more to
miss, and it leaves the DB able to accept an unnormalised value from anywhere
else — including a peer's export.

### D2. Normalisation is automatic; merging is not

A row whose relpath normalises to a form no other row holds is rewritten in
place at `init_db`. That destroys nothing: the string names the same file.

A row whose normalised form **collides** with another row is left ALONE and
reported loudly. Normalising it would violate the UNIQUE constraint, and
resolving that collision means merging two sources and everything hanging off
them — the user's data. That stays an explicit command.

### D3. The merge is explicit, rehearsed, and dry-run by default

`wiki sources dedupe-paths` reports what it would do and changes nothing.
`--apply` performs it. The rehearsal runs against a COPY of the live database and
its output is recorded in the evidence ledger before anything touches the real
one.

Merge rule: keep the **lowest id** (the first registration), repoint every
child row to it, and delete the loser. `sync_key` of the survivor is kept, so the
transport identity is stable for peers.

### D4. Case folding is measured, not fixed

Report how many pairs collide under case folding, so the next decision is made on
numbers rather than on the fact that we happened to be in the file.

## 5. Stop Conditions

Stop and report if the rehearsal shows any child table this plan did not
enumerate, or if the two rows of a colliding pair disagree on `content_hash` —
that would mean they are not the same file and merging would destroy something.

## 6. Execution Phases

- **P1** — `normalize_relpath` + the source-guard test + every write/compare site.
- **P2** — automatic in-place normalisation at `init_db`, skipping collisions and
  reporting them.
- **P3** — `wiki sources dedupe-paths`, dry-run by default, with the child-table
  repoint enumerated from the schema rather than hardcoded.
- **P4** — rehearsal on a copy of the live DB; evidence ledger.
- **P5** — apply to the user's vault (approved 2026-09-01), docs, version bump,
  CHANGELOG.

# RELAY

**Branch:** `release/v0.78.0` — pushed, PR open, awaiting review + CI.

## What shipped

ROADMAP E6. One file could register twice because macOS `readdir` returns a
different Unicode form of the same path than everything else produces. Measured:
18 of 50 relpaths NFD, one pair already split into two `curated` sources sharing
one `content_hash`.

Bigger than the ROADMAP entry said: `db_sync` reconciles peers BY RELPATH, so two
devices in different forms never collide and the peer's rows attach to a fresh
duplicate. It is a cross-device duplication mechanism.

Prevention shipped, and the existing pair was merged with the user's approval
after a full backup. Live vault: 50 → 49 sources, NFD 18 → 0, collisions 1 → 0.

## Two things worth carrying forward

- **The rehearsal caught a UNIQUE collision** the code would have half-applied
  against real data. Rehearse migrations on a copy, always.
- **The apply caught what the rehearsal could not**: `wiki add` never calls
  `init_db`, so pairing canonicalisation there left the ingest path reading stale
  forms — the change would have manufactured the duplicates it removes. Every
  test builds its database fresh, so no test could have said so.

## Status

- [x] Implementation, guards, docs (EN then KR), SCHEMA §6.1, version, CHANGELOG
- [x] Local gates: pytest 1903, vitest 1234, ruff, mypy
- [x] Rehearsed, then applied to the live vault with approval
- [ ] `/code-review:code-review <PR#>` — MANDATORY before merge
- [ ] CI green, then merge

## Next

E2 — chunk size and reindex, already approved by the user. Note it re-embeds the
corpus, so it comes after this.

## Known gaps recorded, not fixed

- 64 pre-existing orphaned child rows (`source_id` 32 and 0). Not created by this
  release; folding an unrelated repair into a data migration makes the migration
  unreviewable. → ROADMAP.
- `db/sources.py`'s one unnormalised lookup, frozen by the D2 holdout record.
  Read-only with a `content_hash` fallback. Close it when the freeze lifts.

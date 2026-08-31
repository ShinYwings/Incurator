# v0.78.0 Evidence Ledger

## Rollback anchor

`master` at `4f94461` (v0.77.0). Branch `release/v0.78.0`.

## Reality as measured, live vault, 2026-09-01

| Fact | Value |
|---|---|
| sources | 50 |
| relpaths stored NFD | 18 (36%) |
| collision groups | 1 |
| the colliding pair | id 35 (NFC) and id 46 (NFD), both `curated` |
| their content_hash | identical — `16d1e9b33723…` |
| `WHERE relpath` sites | 8 |
| sites deriving a relpath from a Path | 33 |
| child tables carrying `source_id` | 12, read from the schema |

## What the rehearsal found, before anything touched real data

Run against a **copy** of the live database.

**First attempt failed**, which is the entire reason for rehearsing:

```
sqlite3.IntegrityError: UNIQUE constraint failed:
  source_pdf_pages.source_id, source_pdf_pages.page_number
```

`source_pdf_pages` is UNIQUE on `(source_id, page_number)` and both sources hold
the same pages, so a plain repoint collides. A migration that had gone straight
at the real database would have half-applied and stopped.

Fixed by moving what fits and dropping what the survivor already holds — the two
rows share a `content_hash`, so their derived rows are the same rows twice.
Counted separately, because "moved" and "dropped as duplicate" are different
facts.

## Rehearsal result, second run

```
before:     50 sources, 1 collision group
normalise:  17 rewritten, 1 skipped (the collision)
merged:     keep=35, remove=[46]
            moved   160 rows across 6 tables
            dropped  94 rows the survivor already had
                     source_pdf_pages 12, source_spans 82
after:      49 sources (1 removed), 0 still NFD, 0 collisions
foreign_key_check: clean
integrity_check:   ok
```

## The 64 orphaned child rows are NOT ours

The post-merge check reported 64 child rows pointing at a missing source. They
point at `source_id` **32** and **0** — not at 46, the row the merge removes.

Verified against the **untouched** database, opened read-only: the same 64 rows
are already orphaned there (`compiler_generations` 1, `ingest_jobs` 1,
`knowledge_units` 62). The migration creates none and removes none.

Recorded rather than fixed here: it is a pre-existing defect with a different
cause, and folding an unrelated repair into a data migration is how a migration
stops being reviewable. → ROADMAP.

## Pre-change baseline

- backend pytest 1902 passed / 7 skipped
- ruff clean, mypy clean over 133 files

## Post-apply results

_(filled in after the approved apply)_

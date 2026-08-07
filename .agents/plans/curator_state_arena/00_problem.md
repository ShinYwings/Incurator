# Briefing: `.curator` State Audit → Arena Diagnosis

Date: 2026-08-06 | master @ `02faa0a` (v0.46.0)
Method (user's direction): investigate the REAL `.curator` state of the live
`second_brain` vault first, then debate whether the observed flow matches the
system documentation and what edge cases break it.

## Why this method

The previous Arena audited code against specs and missed the single biggest
defect in the project — the ≥2 relation-corroboration gate that quarantined
99.3% of the graph — precisely because **the code conformed to the spec**. Every
high-value finding since has come from measuring the real vault instead:
the corroboration gate, the 10 silently-`skipped` sources, the dead source row
behind 48 lint errors. Start from the artifacts, not the source.

## Ground Rules

1. **Read-only.** Do NOT modify code, docs, config, the vault, or the DB. Your
   only write is your own arena document in this folder.
2. The live DB is **read-only** at
   `file:/Users/shin/shinywings/Incurator/.cache/vaults/13ed51f8b06cb88e/state.sqlite?mode=ro`.
   Never open it writable. Never run a mutating `wiki` command.
3. Every finding needs evidence you measured yourself — a query result, a file
   size, a byte count — plus the `file:line` of the code that produces it.
   Assertions without measurement are inadmissible.
4. Check `backend/tests/` and plugin `*.test.ts` before filing: if a test already
   pins the correct behaviour, your claim is wrong or needs a sharper scenario.
5. Specs are authoritative: `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`,
   `docs/specs/curator_schema/SCHEMA.md`,
   `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`,
   `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`. A spec that describes
   something the artifacts contradict is a finding — both are wrong until
   reconciled.
6. Severity: P0 data loss/corruption or serving wrong knowledge; P1 user-visible
   breakage with no workaround; P2 contract violation, silent degradation, or
   unbounded growth; P3 hygiene/doc drift. Max 6 findings each — depth over
   breadth.

## Measured Reality (already established — do NOT re-derive, DO go deeper)

### The vault's `.curator/` contents

| item | size | last written |
|---|---|---|
| `sync/` (2 × `.jsonl`) | **24 MB** | 2026-07-19, 2026-08-06 |
| `sessions.json` | **15 MB** | 2026-08-06 |
| `Collections/` | 6.5 MB | — |
| `overview.md` | 120 KB | 2026-08-05 |
| `sync-report.json` | 100 KB | **2026-07-02** |
| `index.md` | 60 KB | 2026-08-05 |
| `runtime/` | 40 KB | — |
| `state.sqlite` | **0 bytes** | 2026-07-30 |

### Finding-grade observations to start from

**A. `.curator/state.sqlite` is an empty file; the real 79 MB DB is elsewhere.**
`cfg.paths_from_config()` resolves `state_db` to
`<repo>/.cache/vaults/13ed51f8b06cb88e/state.sqlite` (79,134,720 bytes). The
vault holds a 0-byte file of the same name. CLAUDE.md and the architecture notes
say `state.sqlite` is the single source of truth and place it under `.curator/`.

**B. `sessions.json` is 15 MB, of which message text is 334 KB (2.4%).**
11 sessions, 236 messages, 292 `contextRefs`. Byte breakdown:

| field | bytes |
|---|---|
| `contextRefs` | **11,391,376** |
| `content` | 347,387 |
| everything else | ~10,600 |

By ref type: `pdf-page` 125 refs / 9.0 MB / **72 KB avg**; `file` 145 refs /
2.4 MB / 16 KB avg. The largest single ref carries a **1,392,138-byte
`imageBase64`** field. The same file is re-attached and re-stored up to 43×.
`deletedSessionIds` holds 50 entries.

**C. `.curator/sync/` holds 40,864 JSONL lines across two device journals**
(16 MB + 8.1 MB), the older untouched since 2026-07-19. Row 1 of the newer file
is a `deleted_records` tombstone; the header declares `schema_version: 13`.

**D. Derived projections agree with each other but not quite with the DB.**
`index.md`, `overview.md`, and `Collections/` all reference 1372 node ids;
the DB has 1371 live nodes. (The known 1-node gap is the orphan
`CTX-f349d7bf` left by a re-ingest — already filed. Do not re-report it; do ask
what else could produce this class of drift.)

**E. Several `.curator` artifacts have not been rewritten in over a month**
while the vault was actively built: `sync-report.json` and `log.md` (2026-07-02),
`sync_state.json` (2026-07-06).

## Inspector Domains

1. `storage_topology` — Observation A. Where state actually lives vs where every
   doc says it lives; what that means for vault backup, Obsidian sync, the
   `.cache` being repo-local rather than vault-local, multi-vault, and vault
   move/rename. Is the 0-byte file load-bearing, a leftover, or a trap?
2. `session_state` — Observation B. `sessions.json` growth, read/write cost per
   chat operation, atomicity, base64 image retention, ref duplication,
   `deletedSessionIds` retention, and what the plugin schema promises about
   session storage.
3. `sync_journals` — Observation C. Journal growth and compaction, tombstone
   retention, `schema_version` drift, the stale device file, and what happens on
   import/export as these files grow.
4. `derived_consistency` — Observations D and E. What guarantees the derived
   projections (`Collections/`, `index.md`, `overview.md`, `runtime/*.json`,
   `log.md`, `ledger.md`) stay consistent with the DB, when each is rewritten,
   and which are silently never refreshed.

## Debate Protocol

Each inspector writes `01_proposal_<domain>.md` in this folder. Red-teamers then
write `02_critique_<domain>.md` trying to REFUTE each finding (wrong measurement?
already tested? misread spec? unreachable? wrong severity?). Only survivors reach
the synthesis.

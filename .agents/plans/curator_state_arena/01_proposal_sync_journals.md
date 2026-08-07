# Inspector Report: `sync_journals` (Observation C)

Domain: `.curator/sync/` — two device JSONL journals, 24 MB / 40,864 lines total.
Read-only investigation. No code, docs, config, vault, or DB writes made.

## Method

Read `backend/src/curator/db_sync.py` in full (1765 lines), `db/schema.py`'s
`deleted_records` DDL, `commands/db.py`'s `db_autosync` CLI surface, and
`SYSTEM_BEHAVIOR.md` §13.1–13.3. Measured both live journal files directly with
`wc -l`, a Python JSONL row-type/byte-size scan, and a same-connection read-only
query against the live DB
(`file:/Users/shin/shinywings/Incurator/.cache/vaults/13ed51f8b06cb88e/state.sqlite?mode=ro`)
to compare exported row counts table-by-table against live row counts.

## Ground-truth measurements

```
dev-28e419df29f2.jsonl   16,402,744 bytes   29,006 lines (1 header + 29,005 rows)
dev-bd8d7f0753da.jsonl    8,443,943 bytes   11,858 lines (1 header + 11,857 rows)
```

Newer file header: `{"schema_version": 13, "export_id": "565f2d1d…", "exported_at": "2026-08-06T06:03:11Z"}`
Older file header: `{"schema_version": 12, "export_id": "73ba943a…", "exported_at": "2026-07-19T10:56:46Z"}`

Row-type distribution, newer file (29,005 rows / 16,373,610 payload bytes, header excluded):

| table | rows | bytes | avg row |
|---|---:|---:|---:|
| deleted_records | 9,578 | 1,606,593 | 168 |
| query_traces | 57 | 3,680,743 | 64,574 |
| knowledge_units | 2,799 | 2,193,115 | 784 |
| graph_relation_supports | 4,638 | 2,149,364 | 463 |
| source_spans | 2,363 | 1,692,392 | 716 |
| claim_supports | 3,200 | 1,236,985 | 387 |
| prompt_runs | 516 | 758,113 | 1,469 |
| artifact_dependencies | 2,492 | 664,792 | 267 |
| community_reports | 240 | 607,427 | 2,531 |
| (remainder: graph_relations, graph_entities, source_pdf_pages, dag_edges, synthesis_nodes, compiler_generations, sources, source_pages) | 2,065 | 1,783,486 | — |

**These per-table row counts are byte-for-byte identical to a live query against
`state.sqlite`** (e.g. `deleted_records`=9,578 both places, `sources`=36 both
places, `source_spans`=2,363 both places) — confirming the newer journal is a
complete, current full-table dump, not an incremental delta.

## Findings

### F1 — [P2] Full snapshot on every mutating command, uncompressed, with zero compaction

**My measurement:** `export_for_device()` (`backend/src/curator/db_sync.py:1465-1492`)
writes the *entire* `SYNC_TABLES` set every call via `export_knowledge()`
(`db_sync.py:680-781`), then `os.replace()`s the whole file
(`db_sync.py:777`). The docstring confirms intent: *"A full snapshot (not a
delta) is written so a late-joining peer always receives the complete view"*
(`db_sync.py:1473-1476`). `SYSTEM_BEHAVIOR.md:1259-1261` states the same
design. I confirmed empirically (table above) that the 16.4 MB file **is**
that full snapshot — every row in the live DB, every time.

This export runs from the CLI export hook on **every** `wiki add`, `wiki
build`, `wiki sync` (including default incremental), and `wiki update`
(`SYSTEM_BEHAVIOR.md:1338-1345`, wired via `maybe_auto_export()` at
`ingest_worker.py:282`), plus plugin-side triggers on vault load, peer
file-watch, and a 60s poll (`SYSTEM_BEHAVIOR.md:1326-1332`). So a single
`wiki add` of one new source rewrites the full multi-MB snapshot from
scratch.

`export_knowledge()` already has a `compress: bool` parameter
(`db_sync.py:686,712-715`) that gzips output, but it is **only** wired to the
manual `wiki db export --compress` flag (`commands/db.py:30,41,44`).
`export_for_device()` — the function every autosync/CLI-hook/plugin path
actually calls — never passes `compress=True` (`db_sync.py:1485`). I measured
`gzip -9` on the live 16,402,744-byte file: **1,663,943 bytes, a 9.86×
reduction**, sitting unused on the one code path that matters for the 24 MB
under review.

**Failure scenario:** at 10× the current source count (360 sources), the
source-proportional portion of the export (everything except
`deleted_records` and `query_traces`, which don't scale with source count —
see F2/F3) is 11,086,274 bytes today; scaled ~10× that alone is ~111 MB.
Every single incremental `wiki add` of one source then rewrites a >100 MB
file end-to-end, and Syncthing must re-propagate that full file to every peer
on every such rewrite — with a 9.86× compression win sitting unused in the
same module.

### F2 — [P2] `deleted_records` tombstones never expire; already 33% of exported rows, driven by re-ingestion churn, not source growth

**My measurement:** `deleted_records` DDL (`db/schema.py:724-740`) has no TTL
column, no retention field, and no companion cleanup job. Grepping
`db_sync.py` for `DELETE FROM deleted_records` finds exactly two call sites:
`clear_row_tombstone_on_connection` (`db_sync.py:484-541`, delete at line 539)
and `_row_is_blocked_by_tombstone` (`db_sync.py:1216-1262`, delete at line
1259) — both fire only when a **specific row is explicitly reinserted with a
timestamp newer than its own tombstone** (an "undelete" case). Neither is a
bulk or age-based purge; there is no code path anywhere in the module that
prunes tombstones by age.

I broke down the 9,578 live tombstones by target table:

```
source_spans          8,696  (90.8%)
source_pdf_pages        673
claim_supports          199
artifact_dependencies     5
synthesis_nodes           3
sources                   1
source_pages              1
```

91% of all tombstones target `source_spans` — and there are only 2,363
*live* `source_spans` today, meaning 8,696 spans were created and then
deleted, almost certainly by re-ingestion/`wiki build --force` cycles
regenerating spans for the same sources. Tombstone count is **driven by edit
frequency, not source count**, and per `SYSTEM_BEHAVIOR.md:1352-1360` every
export includes 100% of `deleted_records` unconditionally ("including
`deleted_records`, so a delete-only change… still publishes"). This table can
only grow for the life of the vault.

**Failure scenario:** a user who periodically re-ingests/rebuilds existing
sources (a normal workflow, not an edge case) accumulates tombstones far
faster than the "10× sources" baseline suggests — the current vault already
shows a 3.7:1 dead:live ratio for spans. If that ratio holds, 10× the current
re-ingestion activity puts `deleted_records` alone north of 16 MB per device
file, forever, with no way to shrink it short of manual DB surgery outside
any documented tool.

### F3 — [P2] `query_traces` has no retention cap; rows up to 186 KB, usage-driven, 22% of journal bytes at only 57 rows

**My measurement:** `query_traces` schema (`db/schema.py:703-721`) stores
`retrieval_trace_json`/`evidence_json` per query with no row limit anywhere —
grepping all `query_traces` call sites (`db/_entities.py:3300-3386`,
`commands/plugin.py:851`) turns up only `INSERT`, `SELECT`, and a
`list_query_traces` reader with a caller-supplied `LIMIT` for *display*; no
`DELETE`/prune call exists for this table in the codebase. I measured the
per-row size distribution in the live journal: **min 2,768 B, median 52,366
B, max 186,240 B** across 57 rows, totaling 3,680,743 bytes — **22.5% of the
16.37 MB payload from 0.2% of the rows**.

This table doesn't scale with source count at all — it scales with how many
times the user runs `wiki query`. Because it's in `SYNC_TABLES`
(`db_sync.py:46`) and not in `EXCLUDE_TABLES` (`db_sync.py:67-79`), every
query trace ever recorded is retransmitted in full on every single export,
forever.

**Failure scenario:** a power user who queries frequently (this is the
system's primary read interface) can dwarf all knowledge-graph growth with
retrieval telemetry alone — 500 more queries at the measured median (52 KB)
adds ~26 MB to the journal independent of any change to the knowledge base,
with no existing knob to cap or expire it.

### F4 — [P2] Stale/incompatible peer journal is silently and permanently orphaned; `wiki db autosync` reports no signal

**My measurement:** `_read_export_id()` (`db_sync.py:1517-1563`) reads only
the peer file's header line; on `schema_version` mismatch it calls
`logger.info(...)` (`db_sync.py:1553-1556`, INFO level, not raised, not
returned as an error) and returns `None`. `import_all_peers()`
(`db_sync.py:1566-1609`) then does `if export_id is None: continue` at line
1591 — the file is skipped and **never added to the `results` dict**. The CLI
command `db_autosync` (`commands/db.py:99-154`) builds its entire printed and
`--json` summary (`imported_files`, `inserted`, `updated`, `deleted`,
`conflicts`) from that same `results`/`res.imported` structure
(`commands/db.py:119-131`) — a schema-incompatible peer file contributes
**nothing** to any user-visible output. There is no "N peer file(s) skipped"
line anywhere in this command.

I confirmed this is exactly the older file's state: `dev-bd8d7f0753da.jsonl`
is schema_version 12 against a local schema of 13, last written
2026-07-19 — 18 days stale as of this vault's most recent activity
(2026-08-06). `_peer_files()` (`db_sync.py:1495-1514`) enumerates it on every
autosync pass (confirmed it's not filtered by name/pattern, only by "is it my
own file" and "is it a `.sync-conflict-*` file"), so its header **is**
re-read every single run — but only the first line (cheap I/O, not the full
8.1 MB) — and it is silently discarded every time.
`SYSTEM_BEHAVIOR.md:1293-1295` documents the schema-gate mechanic itself
("v12 and v13 peer files are not partially imported… each device must
publish a new v13 snapshot") but never addresses what happens if that device
never comes back to publish one — spec and code agree on the mechanism, and
both are silent on the retention/notice question.

**Failure scenario:** a user retires or loses the device that wrote
`dev-bd8d7f0753da.jsonl` after it last exported on 2026-07-19 holding 33
sources' worth of that device's view. `wiki db autosync`'s output
(`+X inserted, ~Y updated, Z deleted from N peer file(s)`) never mentions the
stuck file, so the user has no signal that this device's knowledge — whatever
in it never made it to a third device before that date — is permanently
excluded. The command reports success and gives false confidence that "all
devices are in sync."

### F5 — [P3] `SYSTEM_BEHAVIOR.md` §13.1–13.3 documents the sync mechanism in detail but is silent on lifecycle/retention for an artifact already at 24 MB

**Quoted spec text:** §13.1 covers full-snapshot semantics ("The exported
file is a **full snapshot** (not a delta)…", `SYSTEM_BEHAVIOR.md:1259-1261`),
tombstone/LWW conflict resolution (`:1263-1291`), the schema gate
(`:1293-1295`), loop prevention (`:1308-1324`), triggers (`:1326-1336`), the
CLI export hook (`:1338-1350`), the export gate
(`:1352-1360`), dry-run observability (`:1362-1366`), and Syncthing conflict
files (`:1368-1377`). §13.3 covers device-local sync state file format and
corruption handling (`:1379-1400`).

**What is absent:** no section addresses compaction, tombstone garbage
collection, a size/row bound on any `SYNC_TABLES` member, retention for
`query_traces`, or what a stale/never-returning peer file means for sync
health or user notification — the exact gaps measured in F1–F4. This is not
a spec/code mismatch (code and spec agree — neither implements nor documents
any of this), but per the briefing's rule 5 ("A spec that describes something
the artifacts contradict is a finding — both are wrong until reconciled"),
the artifact (24 MB, growing, 33% dead tombstone rows, one permanently
orphaned peer file) has already outgrown what the spec describes as a
lightweight "harmless device-local file"
(`SYSTEM_BEHAVIOR.md:1345`, USER_GUIDE.md:995 "Without Syncthing the export
is just a harmless local file") without either document ever revisiting that
characterization as the mechanism scales.

## Summary of severities

| # | Finding | Severity |
|---|---|---|
| F1 | Full uncompressed snapshot rewritten on every mutation; 9.86× compression unused on the live path | P2 |
| F2 | `deleted_records` tombstones permanent, re-ingestion-driven, 33% of rows today | P2 |
| F3 | `query_traces` unbounded, usage-driven, rows up to 186 KB, 22% of bytes at 57 rows | P2 |
| F4 | Stale schema-mismatched peer file silently orphaned forever, zero user-facing signal | P2 |
| F5 | Spec documents the mechanism in depth but never addresses lifecycle/retention at this scale | P3 |

All four P2 findings share one root cause worth flagging to the synthesis
debate explicitly: **the transport format (full JSONL snapshot) and the
retention policy (none) were designed together for correctness at small
scale, and nothing in the reviewed code or docs bounds either dimension as
the vault grows** — not size, not row count, not peer-file age, not query
volume.

# Synthesis — `.curator` State Audit Arena

Date: 2026-08-06 | master @ `02faa0a` (v0.46.0)
Inputs: 4 inspector proposals, 2 red-team critiques, plus my own verification of
the highest-consequence finding.

## The method paid off

Starting from the artifacts instead of from code-vs-spec produced findings the
previous Arena structurally could not reach. The single most consequential one —
a month-dead status file the chat sidebar still polls — is invisible to any
conformance review, because the reader and the writer are each individually
correct. Only comparing two real files on disk exposes it.

The debate also worked in the direction that matters: the red team **downgraded
both P0s to P1** on evidence, and **refuted one finding outright**. Both
corrections are load-bearing and are recorded below rather than quietly dropped.

## Confirmed, ranked

### 1. [P1] The chat sidebar's job/status indicator has been dead for a month

`ChatSidebarView.ts:465-491` reads `<vaultRoot>/.curator/runtime/jobs.json` and
`status.json` through a hardcoded vault-relative path, polled every 2 s. Commit
`6556fc5` (2026-07-06) moved the backend's runtime snapshots into the repo-local
cache. The vault-side files were never migrated and nothing rewrites them.

**Verified independently, not taken on report:**

| file | mtime | content |
|---|---|---|
| `<vault>/.curator/runtime/jobs.json` | **2026-07-04** | `running: 0, idle: true` |
| `<cache>/runtime/jobs.json` | 2026-08-05 | `running: 1, idle: false` |

So the sidebar has shown "idle" continuously since 4 July regardless of what the
backend is doing. **This is the user's own earlier report** — that the build
indicator appears briefly and then stops — and it was never a UI timing bug.

The fix is NOT to correct the path: the red team confirmed the plugin contains
zero vault-key-hashing logic, so it cannot compute the cache location. The
sibling `incuratorDashboardModal.ts` already solved this correctly by calling
`wiki status --json`; the sidebar must do the same.

### 2. [P1] Losing `.cache/` looks like an empty vault, not a broken install

`db/schema.py` `connect()` runs `executescript(SCHEMA_SQL)` on any empty or
missing DB file unconditionally, and `db.get_stats` then returns zeroed counts
rather than raising. Re-clone the repo, wipe the cache, or run in ephemeral CI
and the system reports a healthy, empty vault.

**Red-team correction, accepted:** this is P1, not P0. `.curator/sync/*.jsonl`
lives *inside* the vault, is written on every mutating command by default, and
carries `SYNC_TABLES` — `source_spans`, `knowledge_units`, `community_reports`,
`dag_edges`, and the graph tables. `wiki db import` restores from it. Only
`ingest_jobs`/`job_events`/`ingest_runs` and regenerable embeddings are
genuinely unrecoverable. "Total and unrecoverable" was measurably false.

The real defect is therefore **silence plus undocumented recovery**, not data
loss: nothing warns that the authoritative store vanished, and nothing tells the
user that the vault-side journal can rebuild it.

### 3. [P1] Vault rename or move silently orphans the database

The cache key is `sha256(resolved_vault_root)[:16]`, so renaming or moving the
vault mints a new, empty cache and self-heals a fresh schema into it. Also
reachable through the project's own documented dev command: `VAULT_ROOT=testbed`
resolves relative to the invoking cwd, so the same "testbed" run from two
directories gets two disjoint, mutually invisible databases.

**Red-team correction, accepted:** P1, not P0 — the old cache remains untouched
under its old hash and the key is a deterministic function of the old path, so
recovery is mechanical once you know to look.

### 4. [P2] `sessions.json` is 15 MB of which 81% is re-embedded context

`buildAutoContextRefs` rebuilds full-content refs on every send with no
cross-message dedup: one 12 KB note is stored 52 times (577 KB), and 125
`pdf-page` refs carry full-resolution `imageBase64`, the largest 1,392,138 bytes.
Message text is 334 KB of the 14 MB file.

Each `saveSessionData()` reads and reparses the whole file; the red team
re-derived the real cost as **2 reads / 5 parses / 3 stringifies per save,
≈275 ms, and ≈1.1 s per `sendMessage`** — higher than the inspector's estimate,
scaling linearly. It also found a free ~20% win: a redundant re-stringify+parse
at `sessionStore.ts:73-75`.

The apparent 30-session cap is a **provable no-op** — eviction writes no
tombstone, so the union-merge re-absorbs the evicted session on the next save.
The red team's warning is recorded: "add a tombstone on evict" would cause
permanent data loss; bound the content, not the session count.

### 5. [P2] Sync journals grow without bound and never compact

`export_for_device` writes a full uncompressed table snapshot, triggered once
per completed ingest job (`ingest_worker.py:282` — not per CLI command as first
filed). 24 MB today. `compress=True` already exists on the sibling export path
and is unused; gzip measured **9.86×** (16.4 MB → 1.66 MB), independently
reproduced by both agents. Enabling it is not a free flip: the peer-discovery
glob and filename suffix must change together.

Tombstones never expire — 9,578 live, 90.8% targeting `source_spans`, so growth
tracks re-ingestion churn rather than source count. `query_traces` rows run to
186 KB and are 22.5% of journal bytes from 57 rows; SCHEMA groups it with four
sibling tables that are all in `EXCLUDE_TABLES`, making it the outlier — but it
is not regenerable, so the fix is a retention cap, not exclusion.

A peer journal untouched since 2026-07-19 is skipped forever at INFO level while
`wiki db autosync` reports success — false confidence that all devices are
in sync.

### 6. [P2] Several derived artifacts are never rewritten

`sync-report.json`'s writer is unreachable from the background worker, so it goes
stale under the CLI's own documented default (`wiki build` without `--wait`) —
28 days measured. `wiki sync`'s `finalize_routing_tables` and its success message
both claim to rebuild `ledger.md`/`overview.md`; the function body calls neither.
`overview.md`/`index.md` re-parse every node's frontmatter on every ingest with
no diffing.

### 7. [P3] The docs contradict themselves about where state lives

`CLAUDE.md:415-433` and `SYSTEM_BEHAVIOR.md` §22.3 both place `state.sqlite`
inside `.curator/`, contradicting the correct `SCHEMA.md:17-58` **and
contradicting SYSTEM_BEHAVIOR's own §2.1/§13.1** — a self-contradiction inside
the document the project calls the authority on behaviour. `.stignore` is
write-once and still lists the dead `.curator/state.sqlite` path.

## Refuted — recorded so nobody re-files it

**"Auto-attached PDF context violates PLUGIN_SCHEMA §1308."** The inspector
filed this as contested and asked for adjudication. The red team resolved it
against the finding: `PLUGIN_SCHEMA.md:52` explicitly separates `SessionData`
from "transient PDF.js extraction (never written to `.curator/`)", and a literal
reading would contradict the immediately following bullets. The rule scopes to
DAG registration, not chat storage. The residual defect is the doc's overloaded
use of "`.curator/`" — P3 wording, not a violation.

## Sequencing

1. **The dead status file first.** It is the only finding that already produced a
   user-visible symptom, and the fix is small and self-contained: call
   `wiki status --json` the way the dashboard modal already does.
2. **Then the silent-empty-vault guard** — warn when the authoritative DB is
   absent or zero-byte instead of self-healing quietly, and document the
   journal recovery path. Cheap, and it converts a silent P1 into a visible one.
3. **Then session bloat**, which is the largest measured resource problem and
   already has a roadmap slot ("Chat Session Context Compaction") that this
   audit has now furnished with hard numbers.
4. **Then journal compaction and retention**, where the 9.86× win is already
   measured but needs the filename/discovery change to land with it.
5. **Doc reconciliation** rides with whichever batch touches each surface.

# sync_db Proposal: Five Convergence & Durability Defects in the Cross-Device Sync Layer
Date: 2026-08-04 | Agent Persona: Distributed State Auditor

Scope audited: `backend/src/curator/db_sync.py`, `backend/src/curator/durable_io.py`,
`backend/src/curator/secret_store.py`, `backend/src/curator/db/schema.py`,
`backend/src/curator/db/sources.py`.
Spec ranges read: SYSTEM_BEHAVIOR §13.1/§13.3 (lines 1141–1338), SYSTEM_BEHAVIOR §11.1
secret/config lock + atomic-write + mode-bit contract (lines 713–805), SCHEMA §11.17
composite tombstone codec and portable transport identity (lines 1471–1585).

CAND-01…CAND-06 are not re-reported. I re-swept the *class* of CAND-03
(cross-filesystem `Path.rename`) and confirmed the other three publish/replace paths
are safe — `export_knowledge` (`db_sync.py:708-779`), `write_sync_state`
(`db_sync.py:661-666`) and `durable_io.atomic_write_text` (`durable_io.py:71-94`) all
create their temp sibling in the *same* directory as the target, so no `os.replace`
there can hit `EXDEV`. Do not widen CAND-03 to them.

---

## 1. Core Logic & Implementation

### sync_db-1 [P1] — `INSERT OR IGNORE` in `_do_insert`: an imported row that collides on a *secondary* UNIQUE index is silently discarded and still counted as `inserted`

`backend/src/curator/db_sync.py:1416-1420`:

```python
def _do_insert(conn: "db.sqlite3.Connection", table: str, row: dict) -> None:
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" * len(row))
    conn.execute(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})", list(row.values()))
```

and its only "row is new" caller, `_lw_upsert` (`db_sync.py:1351-1360`):

```python
        where = " AND ".join(f"{key} IS ?" for key in key_columns)
        existing = conn.execute(
            f"SELECT * FROM {table_name} WHERE {where}",
            tuple(row[key] for key in key_columns),
        ).fetchone()

        if existing is None:
            if not dry_run:
                _do_insert(conn, table_name, row)
            return "inserted"
```

The existence probe uses the **primary key only** (`primary_keys` comes from
`PRAGMA table_info`, `db_sync.py:836-843`). The insert is then executed with
`OR IGNORE`, and `"inserted"` is returned unconditionally without checking
`conn.total_changes` / `cursor.rowcount`. Any collision on a *secondary* UNIQUE index
is therefore swallowed by SQLite and reported to the user as a successful insert.

Synchronized tables carrying exactly such indexes (`db/schema.py`):

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_source_spans_source_hash        -- line 290
    ON source_spans(source_id, content_hash);
CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_entities_name             -- line 368
    ON graph_entities(canonical_name, entity_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_aliases_resolved         -- line 445
    ON entity_aliases(alias_normalized, entity_id, resolution_status)
    WHERE entity_id IS NOT NULL;
```

**Concrete failure (the normal P2P case, not an edge case).** Device A and device B
each ingest sources mentioning "Transformer". Each mints its own `graph_entities.id`
(`ENT-<uuid>`) with `canonical_name='Transformer', entity_type='concept'`. B imports
A's snapshot: the PK probe on `id` misses, `INSERT OR IGNORE` hits
`idx_graph_entities_name`, SQLite ignores the statement, and `_lw_upsert` returns
`"inserted"` → `stats.inserted += 1` (`db_sync.py:936-937`). The entity is silently
lost, the pass reports success with an inflated insert count, and **every**
`graph_relations` / `graph_relation_supports` / `entity_aliases` row A exported that
references `ENT-A` is now dangling (there is no FK from `graph_relations` to
`graph_entities` — `grep -n "FOREIGN KEY" db/schema.py` shows FKs only on
`source_id`/`job_id`/`doc_id`/`chunk_id`, so nothing rejects the orphan). The same
shape hits `source_spans` whenever both devices ingest the same file
(`(source_id, content_hash)` collides while the span `id` differs), which then leaves
`claim_supports.source_span_id` pointing at a span this replica does not have.
This violates §13.1's convergence promise and SYSTEM_BEHAVIOR §32 (a failed operation
reported as success), and it corrupts the `wiki db autosync` report the plugin shows.

**Sub-case (b): the `sources` variant turns the same line into a permanent wedge.**
`_lw_upsert_source` (`db_sync.py:1289-1302`) uses the same `_do_insert`, then detects
the swallowed conflict by absence and raises:

```python
        _do_insert(conn, "sources", insert_row)
        inserted = conn.execute(
            "SELECT id FROM sources WHERE sync_key = ?", (sync_key,),
        ).fetchone()
        if inserted is None:
            raise ValueError(
                f"Source {sync_key!r} conflicts with an existing local relpath"
            )
```

`sources.relpath` is `TEXT NOT NULL UNIQUE` (`db/schema.py:78`) while `sync_key` has
its own unique index (`db/schema.py:107`), so a peer row with the same `relpath` but a
different `sync_key` — e.g. device A holds a Zotero-mirrored
`04_Resources/paper.pdf` whose key was set explicitly to `zotero:ABCD1234` (the
`sources_set_sync_key` trigger fires only `WHEN NEW.sync_key IS NULL OR NEW.sync_key =
''`, `db/schema.py:719`) while device B added the same file plainly and derived
`vault:04_Resources/paper.pdf` — raises out of `import_knowledge` into
`AutosyncError` (`db_sync.py:1597-1602`). The file transaction correctly rolls back and
the peer is correctly not checkpointed, but the failure is **deterministic**: every
later trigger (startup, `fs.watch`, the 60-s poll, the ribbon action) fails identically,
and because `import_all_peers` raises out of its loop, every peer file sorted *after*
the poisoned one is never imported either. §13.1 promises "Retrying the pass is safe
and content-idempotent" — retrying is safe here but can never succeed, and no `wiki db`
subcommand can repair a sync-key/relpath conflict.

*Fix direction.* (i) Stop inferring success: have `_do_insert` return the affected row
count (or use plain `INSERT` and catch `sqlite3.IntegrityError`) and make `_lw_upsert`
map a swallowed insert to an explicit outcome rather than `"inserted"`. (ii) For each
synchronized secondary UNIQUE index, define the merge rule (for `graph_entities` the
natural one is identity merge on `(canonical_name, entity_type)` with remote-id →
local-id remapping, exactly as `sources` already does for `sync_key`; for
`source_spans` merge on `(source_id, content_hash)`). (iii) Report unmergeable rows in
`ImportStats` and let the pass continue to the next peer instead of aborting the whole
chain. Nothing in `backend/tests/test_db_sync.py` or `test_db_autosync.py` currently
asserts on a secondary-UNIQUE collision.

---

### sync_db-2 [P2] — `sources_set_sync_key` in `SCHEMA_SQL` is a no-op (a Python escape ate the backslash), and the trigger drift detector is blind to exactly that fragment

`backend/src/curator/db/schema.py:716-723`, inside the non-raw `SCHEMA_SQL = """…"""`:

```sql
CREATE TRIGGER IF NOT EXISTS sources_set_sync_key
AFTER INSERT ON sources
FOR EACH ROW
WHEN NEW.sync_key IS NULL OR NEW.sync_key = ''
BEGIN
    UPDATE sources SET sync_key = 'vault:' || replace(NEW.relpath, '\', '/') WHERE id = NEW.id;
END;
```

`'\'` in a non-raw string is `'` followed by the escape `\'`, so the SQL that reaches
SQLite is `replace(NEW.relpath, '', '/')`, and SQLite's `replace()` with an empty
pattern returns the input unchanged. The second definition of the same trigger, in
`_refresh_current_triggers` (`db/schema.py:803`), is correct because it doubles the
backslash:

```python
            UPDATE sources SET sync_key = 'vault:' || replace(NEW.relpath, '\\', '/') WHERE id = NEW.id;
```

Verified behaviourally by extracting both string constants with `ast` and executing
them against in-memory SQLite (no repo, vault, or cache state touched):

```text
SCHEMA_SQL -> "… replace(NEW.relpath, '', '/') …"
REFRESH    -> "… replace(NEW.relpath, '\\', '/') …"
relpath = '04_Resources\win\doc.pdf'
  sync_key (SCHEMA_SQL trigger): vault:04_Resources\win\doc.pdf   ← non-portable
  sync_key (refreshed trigger):  vault:04_Resources/win/doc.pdf   ← portable
```

The self-heal path cannot repair it. `_triggers_need_refresh`
(`db/schema.py:843-868`) returns `False` when the stored SQL contains
`NEW.sync_key IS NULL OR NEW.sync_key = ''`, `NEW.sync_key IS OLD.sync_key` and the two
`julianday(OLD.updated_at) + (1.0 / 86400000.0)` fragments — **all of which the broken
body also contains**. So `connect()` (`db/schema.py:891-909`), which runs
`executescript(SCHEMA_SQL)` and then refreshes only `if _triggers_need_refresh(conn)`,
installs the broken trigger and then certifies it as current forever. Only `init_db`
(`db/schema.py:871-886`) refreshes unconditionally, so the exposure is any
`state.sqlite` materialized through the `connect()` self-heal path that
`db/schema.py:901` explicitly advertises ("Self-heal for existing empty/corrupted state
DB files missing base tables").

**Concrete failure.** A Windows device in that state derives
`sync_key = vault:04_Resources\paper.pdf`; its macOS peer derives
`vault:04_Resources/paper.pdf` for the same document. `_lw_upsert_source` resolves by
`sync_key` (`db_sync.py:1285-1288`), misses, and inserts a *second* source row (the
`relpath` values differ too, so the UNIQUE index does not stop it). Both devices now
carry two source rows, two L1→L4 subtrees and two atom sets for one document, and no
LWW rule will ever merge them — a direct violation of SCHEMA §11.17 "Portable source
transport identity (`SCHEMA_VERSION = 12`)".

*Fix direction.* Use `'\\'` (or a raw string) in `SCHEMA_SQL`, and — the real fix —
generate both scripts from one `name -> body` mapping so the two definitions cannot
drift, with `_triggers_need_refresh` comparing `sqlite_master.sql` against the
normalized expected body instead of a hand-picked substring allowlist. Add a
regression test that inserts a backslash `relpath` through a `connect()`-created DB.
`grep -rn "replace(NEW.relpath\|sources_set_sync_key\|_triggers_need_refresh"
backend/tests` returns nothing today.

---

### sync_db-3 [P2] — `last_export_ts` is stamped *after* the snapshot is read, so a row committed during the export is stranded behind a closed export gate

`backend/src/curator/db_sync.py:1481-1492`:

```python
    device_id = get_device_id(internal_dir)
    …
    out = sync_dir / f"dev-{device_id}.jsonl"
    export_knowledge(db_path, out)

    state = read_sync_state(internal_dir)
    state["last_export_ts"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    write_sync_state(internal_dir, state)
```

The gate that decides whether anything is ever published again
(`db_sync.py:1658-1672`):

```python
    newest = _local_max_ts(db_path)
    return bool(newest) and _timestamp_key(newest) >= _timestamp_key(last)
```

`export_knowledge` opens its own connection and streams 25 tables
(`db_sync.py:728-776`), which on a real vault takes seconds. Any row committed by
another process *after* its table was scanned is absent from the snapshot yet carries a
timestamp strictly older than the `last_export_ts` written at line 1488 — so the gate
closes on it.

**Concrete interleaving.** Both triggers are default-on by design (§13.1: the plugin's
`fs.watch` + 60-s poll run `wiki db autosync`; every mutating CLI command runs
`_maybe_auto_export`, `db_sync.py:1675-1686`):

1. `10:00:00.1` — plugin-spawned `wiki db autosync` begins `export_knowledge`;
   `sources` is scanned and written first (it is second in `SYNC_TABLES`).
2. `10:00:01.5` — the user's `wiki add report.pdf` commits a new `sources` row with
   `updated_at = 2026-08-04T10:00:01.500Z`. It is **not** in the in-flight snapshot.
3. `10:00:03` — the export finishes; `last_export_ts = 2026-08-04T10:00:03Z`.
4. `wiki add` reaches its own `_maybe_auto_export`: `10:00:01.5 >= 10:00:03` is
   `False` → no export.
5. The manual "Sync Knowledge DB" ribbon action calls `autosync`, which consults the
   same gate → still `False`. The new source reaches no peer until some *unrelated*
   later mutation happens to reopen the gate.

That is exactly the silent staleness §13.1 records as the v0.30.0 "Dashboard shows 5
sources instead of 31" incident, and it defeats the stated purpose of the `>=`
comparison (SYSTEM_BEHAVIOR:1293-1297: "instead of stranding the mutation until an
unrelated later change").

*Fix direction.* Stamp the export **start**, not its finish. `export_knowledge` already
computes precisely the right value before opening the DB connection
(`db_sync.py:704`: `now = datetime.now(timezone.utc).isoformat(timespec="seconds")…`);
surface it on `ExportStats` (or capture `now` in `export_for_device` before the call)
and persist that as `last_export_ts`. Stamping earlier is strictly safe: worst case it
costs one extra idempotent re-export, which §13.1 already accepts by design.

---

### sync_db-4 [P2] — device-local sync state is an unlocked, non-atomic cross-process read-modify-write; the §11.1 primitives that exist for this are never used by `db_sync`

`backend/src/curator/db_sync.py:656-677`:

```python
def write_sync_state(internal_dir: Path, state: dict) -> None:
    """Persist this device's local sync bookkeeping."""
    p = _sync_state_path(internal_dir)
    _validate_sync_state(state, p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)


def get_device_id(internal_dir: Path) -> str:
    state = read_sync_state(internal_dir)
    device_id = state.get("device_id")
    if not device_id:
        device_id = uuid.uuid4().hex[:12]
        state["device_id"] = device_id
        write_sync_state(internal_dir, state)
    return device_id
```

`durable_io.locked_path` / `durable_io.atomic_write_text` exist for exactly this
contract, and `grep -rn "locked_path\|atomic_write_text" backend/src/curator` shows
they are used **only** by `config.py:400-405` and `secret_store.py:37,74,84,97,113,123`
— never by `db_sync.py`. Every `read_sync_state → mutate → write_sync_state` sequence
(`get_device_id`, `export_for_device:1487-1491`, `import_all_peers:1584-1608`) is an
unserialized RMW over one file shared by concurrent backend processes.

**Concrete interleavings:**

- *Split identity on first use.* Two processes call `get_device_id` before the state
  file exists (plugin startup autosync + a CLI command on a fresh device). Both read
  `{}`, both mint a UUID, both write; last writer wins. The loser has meanwhile already
  published `dev-<idB>.jsonl` into the synchronized `.curator/sync/` tree. That file is
  now an orphan: this device exports only `dev-<idA>.jsonl` and never rewrites
  `dev-<idB>.jsonl`, and because `_peer_files` excludes only `dev-<own>.jsonl`
  (`db_sync.py:1506-1513`) **this device re-imports its own stale former snapshot as a
  phantom peer**, as does every other device, forever. §13.1 names "a device never
  imports its own file" as loop-prevention pillar (b); this breaks it structurally, and
  the phantom device also inflates the dashboard's device count (§13).
- *Lost high-water marks.* `import_all_peers` snapshots `state` at line 1584 and writes
  it back only at line 1608 after all peers. A concurrent `export_for_device` writing
  `last_export_ts` in between is silently reverted by that write-back — and symmetrically
  a concurrent export reverts freshly recorded peer `last_export_id` marks, forcing full
  re-imports of every peer file.

§13.3 requires this state to be fail-closed and to "never … discard peer high-water
marks". The read side is careful (`_validate_sync_state`, `db_sync.py:614-653`); the
write side can drop the same data through a plain lost update, and never fsyncs.

*Fix direction.* Route every sync-state mutation through
`durable_io.locked_path(state_path)` + `durable_io.atomic_write_text`, re-reading under
the lock and merging into the freshly read mapping (the same locked-updater discipline
§11.1 already mandates for `save_config()`). Better still, hold that lock for the whole
`autosync` pass so two local invocations serialize rather than race.

---

### sync_db-5 [P2] — mutable rows have no tie-break, so a same-second concurrent edit diverges permanently; the immutable branch ten lines below already solves this

`backend/src/curator/db_sync.py:1362-1390`:

```python
        if updated_col:
            local_ts = existing[updated_col] or ""
            remote_ts_fn = _REMOTE_TS_FN.get(table_name)
            remote_ts = remote_ts_fn(row) if remote_ts_fn else (row.get(updated_col) or "")
            if _timestamp_key(remote_ts) > _timestamp_key(local_ts):
                …
                return "updated"
            return "skipped"

        local_row = {key: existing[key] for key in row}
        if local_row == row:
            return "skipped"

        # Immutable tables without a revision clock still need deterministic
        # convergence. …
        remote_key = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
        local_key = json.dumps(local_row, sort_keys=True, separators=(",", ":"), default=str)
        if remote_key <= local_key:
            return "skipped"
```

The immutable branch is explicitly convergence-safe. The mutable branch is not: on
`remote_ts == local_ts` with **different content**, each replica keeps its own version
(`_lw_upsert_source:1306-1307` is identical for `sources`). Since every later export
republishes the same timestamps, both devices skip each other forever and never
re-converge — `wiki query` then returns different text for the same node id depending
on which machine you ask, with no warning anywhere.

Ties are not exotic, because the dominant local clock is second-precision
(`db/schema.py:760-763`):

```python
def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
```

and `_now_iso()` is what stamps the LWW columns of the synchronized entity tables
(`db/_entities.py:159, 367, 502, 556, 705, 786, 846, 950, 1184, 1340, 1363, 1461,
1964, …` — `knowledge_units.updated_at`, `graph_entities.updated_at`,
`graph_relations.updated_at`, `community_reports.updated_at`). Two devices touching the
same knowledge unit or entity inside one wall-clock second — trivially reachable when
both run a build, or when a user retries a unit on the laptop while the desktop
compiles — produce byte-identical revisions over different payloads.

SYSTEM_BEHAVIOR §13.1 currently *blesses* this ("A row with the same key and equal/older
LWW revision is `skipped`"), so under arena rule 5 **spec and code are both wrong**: the
spec specifies a divergent outcome and the code implements it faithfully.

*Fix direction.* Give the mutable branch the same deterministic fallback the immutable
branch has: on an exact timestamp tie with unequal payloads, compare canonical JSON and
keep the greater on both sides, counted as a distinct `tie_broken` statistic so it is
observable (§32). Update §13.1 in the same change (docs-first). Moving `_now_iso()` to
millisecond precision lowers the tie probability but cannot remove it, so it is a
complement, not a substitute.

---

## 2. Pros & Cons

### What I judged clean (checked, no finding raised)

- **Composite tombstone codec (SCHEMA §11.17).** `_canonical_composite_key`
  (`db_sync.py:206-249`) and `_decode_composite_key` (`db_sync.py:261-293`) are strict
  in exactly the ways the spec demands: exact field set (no missing/extra), exact scalar
  type via `type(value) is not value_type` (so a JSON `true` is rejected for an `int`
  field), empty-string rejection, an envelope pinned to `set(payload) == {"key","v"}`
  with `v == 1`, duplicate JSON keys rejected through
  `object_pairs_hook=_unique_json_object`, and a re-canonicalization equality check
  (`token != canonical`) that rejects whitespace/ordering variants. Table and column
  identifiers come only from `_COMPOSITE_KEY_SPECS`; JSONL supplies bound values only.
  `_physical_key_for_token` (`db_sync.py:358-383`) correctly returns `None` values when
  the parent source is absent, and `_apply_tombstone` still records the portable
  tombstone in that case (`db_sync.py:1166-1183`), matching §11.17's
  "the portable tombstone is still retained". I could not construct an edge token that
  slips through.
- **Per-file import atomicity.** `import_knowledge` does all work inside one
  `db.connect` block (`db_sync.py:820-943`); `connect` commits only on clean exit and
  its `finally: conn.close()` discards the pending transaction on error
  (`db/schema.py:891-909`). `_apply_tombstone` and `_delete_source_by_sync_key`
  (`db_sync.py:1121-1206`) take the caller's connection and never open their own, so
  §11.17's "DELETE completes before the tombstone is recorded, in one transaction" holds
  and a mid-file failure leaves nothing applied. `test_db_autosync.py:245-267` already
  pins the rollback + no-checkpoint behaviour.
- **Snapshot publication.** `export_knowledge` writes a unique temp sibling in the same
  directory and `os.replace`s it (`db_sync.py:708-779`), so two concurrent local
  exporters cannot publish a torn `dev-*.jsonl`. I checked this specifically before
  filing sync_db-4 and deliberately scoped that finding to the sync-state file only.
- **Header gate / fail-closed reads.** `_read_export_id` (`db_sync.py:1517-1563`)
  returns `None` only for a well-formed incompatible `schema_version` and raises on
  empty/malformed/headerless/`export_id`-less input, matching §11.17's "is not
  checkpointed"; `read_sync_state` + `_validate_sync_state` (`db_sync.py:597-653`) treat
  only `FileNotFoundError` as initialization and reject a missing/null/empty/non-string
  `device_id`, exactly as §13.3 requires.
- **Secret store atomicity/mode bits (§11.1).** `atomic_write_text` opens the temp
  sibling with `os.open(..., O_WRONLY|O_CREAT|O_EXCL, create_mode)`
  (`durable_io.py:73-77`), so a `0600` secret target is `0600` from its first byte, and
  it re-reads and re-applies the existing file's `stat.S_IMODE` for ordinary configs
  (`durable_io.py:60-67, 91-92`). `_read_store` (`secret_store.py:52-69`) raises
  `DurableStateError` for corrupt/unreadable JSON instead of degrading to `{}`, and
  `list_secrets` releases the lock before calling `mask_secret`
  (`secret_store.py:122-125`), so it does not re-enter `flock` on a second descriptor.

### What I could NOT verify

- **Real multi-device execution.** Under the read-only mandate I ran no `wiki` command,
  created no vault, and drove no Syncthing. sync_db-1, -3, -4 and -5 are argued from
  code paths and timing, not reproduced end-to-end. sync_db-2 *was* reproduced, but only
  against in-memory SQLite fed with the two extracted string constants — I did not
  observe a Windows-created `state.sqlite`.
- **Which shipped command can materialize `state.sqlite` through `connect()` rather than
  `init_db`.** I confirmed the asymmetry (`init_db` always refreshes triggers,
  `connect()` refreshes only when `_triggers_need_refresh` says so) but did not
  enumerate every entry point. If no shipped path can reach `connect()` with a missing
  DB, sync_db-2 degrades from "non-portable `sync_key` on Windows" to "two divergent
  definitions of one trigger plus a detector that cannot see the difference" — still a
  real defect, but P3.
- **Windows locking generally** — related, filed here rather than as a numbered finding
  because it needs a product decision on Windows support: `durable_io.py:23`,
  `_fcntl = importlib.import_module("fcntl") if os.name != "nt" else None`, means
  `locked_path` on Windows silently degrades to an in-process `threading.RLock`
  (`durable_io.py:44-53`) with **no** cross-process lock. §11.1 states config and secret
  "read/merge/write mutations are process-locked" and that "concurrent writers cannot
  lose unrelated credentials"; on Windows a plugin-spawned `wiki config set --local`
  racing a user's `wiki config provider` can drop keys with no warning. A
  `msvcrt.locking` branch (or an `O_CREAT|O_EXCL` lock-file fallback) closes it.
- **Unicode path normalization.** `source_pages` tombstone tokens embed `wiki_path`
  verbatim and `sync_key` embeds `relpath`. macOS hands out NFD-decomposed filenames
  while Linux/Windows usually carry NFC, so one file can canonicalize to two different
  portable tokens across devices. I could not confirm whether `relpath`/`wiki_path` are
  normalized upstream, so I did not file it — but it is the same "portable identity is
  not actually portable" family as sync_db-2 and deserves one `unicodedata.normalize`
  check while that fix is being written.

### Cost/benefit and sequencing

- sync_db-2, -3 and -4 are small, bounded and independently testable (a trigger-body
  equality test; a "mutate during export → next gate opens" test with a patched clock; a
  two-process `get_device_id`/`write_sync_state` race test). They belong in one batch.
- sync_db-1 is the highest-value item but needs a *policy* decision per secondary UNIQUE
  index (identity-merge vs. skip-and-report) before any code, so it belongs in the Master
  Plan's locked-design-decisions section. Its cheap half — "never report a swallowed
  insert as `inserted`, and never let one unmergeable row abort the remaining peer
  files" — can ship first and is a strict improvement on its own.
- sync_db-5 requires a synchronized SYSTEM_BEHAVIOR §13.1 edit, so it is the one item
  here that must go docs-first.

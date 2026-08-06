# Critique on `01_proposal_sync_db.md`
Date: 2026-08-04 | Agent Persona: Red-team Distributed-State Critic

Method: every cited `file:line` was re-read at HEAD of `chore/system-defect-audit-arena`.
I did not run `wiki`, did not touch `testbed/`, and wrote no file other than this one.
Each finding was attacked on five axes: (a) is the quoted code real and current;
(b) is the failure actually reachable given upstream guards; (c) is it already pinned
by a test; (d) does the cited spec text really promise what is claimed; (e) is the
severity justified under the §00 rubric.

Verdict summary:

| id | inspector | verdict | final |
|---|---|---|---|
| sync_db-1 | P1 | **confirmed** (sub-case (b) confirmed *via a different mechanism* — the inspector's stated trigger is wrong) | P1 |
| sync_db-2 | P2 | **confirmed** | P2 |
| sync_db-3 | P2 | **confirmed** (stated interleaving is not airtight; replaced with a valid one) | P2 |
| sync_db-4 | P2 | **downgraded** — both spec references are misapplied and every consequence is idempotent/self-limiting | P3 |
| sync_db-5 | P2 | **downgraded** — code matches the spec exactly (no violation), tie window far narrower than claimed, self-heals on the next edit | P3 |

---

## 1. Vulnerabilities & Flaws

### sync_db-1 — CONFIRMED at P1 (with one piece of evidence refuted)

**Code re-verified.** `db_sync.py:1416-1419` is verbatim as quoted: `_do_insert`
issues `INSERT OR IGNORE` and returns `None`, discarding `cursor.rowcount`.
`_lw_upsert` (`db_sync.py:1351-1360`) probes with
`WHERE {key} IS ?` over `key_columns`, which `import_knowledge` supplies from
`PRAGMA table_info` pk columns (`db_sync.py:836-843`), then returns `"inserted"`
unconditionally. `import_knowledge` maps that string straight onto
`stats.inserted += 1` (`db_sync.py:932-937`). All three secondary UNIQUE indexes
exist and are on synchronized tables (`db/schema.py:290, 368, 445`;
`SYNC_TABLES` at `db_sync.py:37-63` includes `source_spans`, `graph_entities`,
`entity_aliases`).

**Reachability — I tried to refute it and could not.** The refutation I looked for
was deterministic ids: if `graph_entities.id` and `source_spans.id` were derived
from their natural key, the PK probe would hit and the secondary index could never
be the *first* collision. They are not. `db/_entities.py:34-36`:

```python
def _new_id(prefix: str) -> str:
    """Generate a typed `<PREFIX>-<UUID8>` id."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"
```

and both call sites mint through it — `chosen_id = entity_id or _new_id("ENT")`
(`db/_entities.py:880`) and `span_id = _new_id("SPAN")` (`db/_entities.py:137`,
inside the helper whose own docstring says spans are keyed on
`(source_id, content_hash)`). So two devices that independently ingest the same
file produce **identical natural keys with different surrogate ids** — exactly the
input that makes the PK probe miss and the secondary index fire.

The `source_spans` variant is the worse half and the inspector under-sold it. Span
`source_id` is remapped to the local id before the upsert
(`db_sync.py:912-922`), so after the two `sources` rows merge on `sync_key`, the
peer's spans collide on `(source_id, content_hash)` against the local spans,
are dropped, and are counted as inserted — while the peer's `claim_supports`
rows (composite-PK, no unique conflict) *do* insert and now carry
`source_span_id` values that name spans this replica does not have. I confirmed
nothing rejects them: `grep -n "FOREIGN KEY" db/schema.py` returns only
lines 122, 137, 147, 188, 287 (`source_id`), 624 (`doc_id`), 659 (`chunk_id`) —
there is no FK from `claim_supports`/`graph_relations` to
`source_spans`/`graph_entities`. That is dangling evidence provenance, i.e.
corruption of the citation graph, not merely a lost row.

**Test check.** `grep -rn "conflicts with an existing local relpath|INSERT OR IGNORE|_do_insert" backend/tests/`
returns only unrelated `source_spans`/`dag_edges` seeding in
`test_plan_b_support.py` and `test_v021_dag_edges.py`. No test in
`test_db_sync.py` or `test_db_autosync.py` constructs a secondary-UNIQUE
collision. The inspector's "nothing pins this" claim is correct.

**Where the inspector is WRONG — sub-case (b)'s stated trigger does not exist.**
The proposal argues the `sources` wedge is reached because a device "set the key
explicitly to `zotero:ABCD1234`". I grepped every non-`db_sync` write of the
column:

```
grep -rn "sync_key" --include=*.py backend/src/curator/ | grep -v db_sync.py
  ingest_raw.py:498,505,2484,2489   -> SELECT only
  ingest_llm.py:277,279,299         -> SELECT only
  db/sources.py:93                  -> SELECT only
  db/schema.py:716-721, 798-803     -> the trigger
```

**No shipped code path ever writes a non-`vault:` `sync_key`.** The column is a
pure function of `relpath` computed by the AFTER-INSERT trigger. So the
"`zotero:` key vs derived key" scenario is fabricated and that evidence must be
struck from the Master Plan.

**But the wedge is real by a different route, which I verified.** The trigger fires
`AFTER INSERT` only, and two shipped paths `UPDATE sources SET relpath = ?`
without touching `sync_key`:

- `source_tools.py:378-381` (reference re-point / move)
- `ingest_raw.py:2267-2278` (external-reference re-registration)

So after a move, a source's `sync_key` stays anchored to its **original** path while
`relpath` names the new one. Now let device B independently register a source at
that new path (its `sync_key` = `vault:<newpath>`). B imports A's row:
`SELECT * FROM sources WHERE sync_key = ?` misses (`db_sync.py:1285-1288`),
`_do_insert` runs with A's `relpath`, hits `sources.relpath TEXT NOT NULL UNIQUE`
(`db/schema.py:78`), `OR IGNORE` swallows it, the re-`SELECT` by `sync_key`
returns `None`, and `raise ValueError(...)` fires (`db_sync.py:1298-1301`).
That propagates through `import_all_peers` → `AutosyncError`.

**The blast radius is bigger than the proposal states.** `import_all_peers` raises
out of the `for` loop at `db_sync.py:1597-1602`, so `write_sync_state(internal_dir, state)`
at `db_sync.py:1606-1607` **never runs** — the `last_export_id` checkpoints for peers
that imported *successfully* earlier in the same pass are discarded too. Every retry
therefore re-imports every earlier peer from scratch and then dies on the same file,
forever, with no `wiki db` subcommand able to repair it. §13.1's
"Retrying the pass is safe and content-idempotent" holds only in the safety sense;
liveness is permanently gone.

**Severity.** Keep P1. Sub-case (a) is silent corruption reported as success, which
under the rubric borders P0 ("data loss/corruption"); I stop short of proposing P0
only because the *local* replica's own knowledge is intact and the damage is confined
to imported cross-references. Sub-case (b) is textbook P1: user-visible breakage
(autosync dead) with no workaround.

---

### sync_db-2 — CONFIRMED at P2

**Code re-verified.** `SCHEMA_SQL` opens at `db/schema.py:70` as a plain
`"""…"""` (non-raw) literal, and line 721 is verbatim
`replace(NEW.relpath, '\', '/')`. In a non-raw literal that is `'` + the escape
`\'` → `'`, so SQLite receives `replace(NEW.relpath, '', '/')`, and SQLite's
`replace()` with an empty pattern returns its input. Line 803 inside
`_refresh_current_triggers` correctly writes `'\\'`. The two definitions really
do disagree.

**Blindness of the detector re-verified.** `_triggers_need_refresh`
(`db/schema.py:843-868`) checks exactly four substrings:
`"NEW.sync_key IS NULL OR NEW.sync_key = ''"`, `"NEW.sync_key IS OLD.sync_key"`,
and the `julianday(OLD.updated_at) + (1.0 / 86400000.0)` fragment in two triggers.
The broken body contains the first fragment and the other three live in triggers
that are byte-identical in both scripts, so the function returns `False` for a DB
carrying the broken `sources_set_sync_key`. Nothing compares the `replace()`
argument.

**The exposure asymmetry re-verified.** `init_db` (`db/schema.py:871-886`) calls
`_refresh_current_triggers(conn)` unconditionally; `connect` (`db/schema.py:891-909`)
calls it only `if _triggers_need_refresh(conn)`. `connect` runs
`db_path.parent.mkdir(parents=True, exist_ok=True)` then `sqlite3.connect(db_path)`,
which **creates the file**, then `executescript(SCHEMA_SQL)` — whose
`CREATE TRIGGER IF NOT EXISTS` installs the broken body. So any `db.connect()`
that beats `db.init_db()` to a given `state.sqlite` permanently bakes in the
broken trigger *and* certifies it as current. `init_db` has only four call sites
(`testbed_manager.py:94`, `mcp/server.py:727`, `commands/core.py:259`,
`commands/core.py:1041`), whereas `db.connect(...)` is the ubiquitous entry point —
so the ordering is a property of whichever command the user runs first, not a
guaranteed invariant.

**Test check.** `grep -rn "sources_set_sync_key|_triggers_need_refresh|replace(NEW.relpath)" backend/tests/`
returns nothing. `test_portable_paths.py:80` only asserts the *column* exists.
Not pinned.

**Where I trim the claim.** The inspector's consequence ("the same document becomes
two unmergeable source rows") is right, but note the failure is symmetric-benign in
one respect: because `relpath` also differs between the two devices
(`04_Resources\p.pdf` vs `04_Resources/p.pdf`), the `relpath` UNIQUE index does
**not** fire, so this does *not* additionally trigger the sync_db-1(b) wedge. The
two findings are independent; do not bundle them as one cause chain.

**Severity.** P2 stands. It is a real code-level defect (two contradictory
definitions of one trigger plus a detector structurally unable to see the
difference) that violates SCHEMA §11.17's portable-identity contract, and the
duplication-without-single-source is itself the defect regardless of whether a
Windows device is in play. Not P1: no currently-supported platform in this
repo's test matrix produces backslash relpaths, so today's realized impact is
latent.

---

### sync_db-3 — CONFIRMED at P2, but the proposal's interleaving is not airtight

**Code and spec re-verified.** `export_for_device` (`db_sync.py:1481-1492`) calls
`export_knowledge(db_path, out)` and only afterwards stamps
`state["last_export_ts"] = datetime.now(...)`. The gate
(`db_sync.py:1670-1672`) is `bool(newest) and _timestamp_key(newest) >= _timestamp_key(last)`.
`autosync` gates its export the same way — `result.would_export = changed or local_has_unexported_changes(...)`
(`db_sync.py:1757-1759`) — so the manual ribbon action and the 60-s poll genuinely
do **not** re-publish once the gate has closed. The spec text is as cited:
SYSTEM_BEHAVIOR §13.1 "Export gate semantics" states `>=` exists "instead of
stranding the mutation until an unrelated later change". Stamping the *finish*
re-opens precisely the hole `>=` was introduced to close.

**Where I attacked it and the proposal's own scenario failed.** Step 4 of the
proposal has `wiki add report.pdf` blocked by its own `_maybe_auto_export`.
That does not hold: `_local_max_ts` takes `MAX` across *all* `SYNC_TABLES`
(`db_sync.py:1640-1655`), and `wiki add` keeps writing L1–L4 rows after the
`sources` row — those later rows carry timestamps past the export's stamp, so the
gate reopens and the source is published. A long-running writer cannot be
stranded this way.

**A valid interleaving I did construct (use this one instead).** The hazard needs
the concurrent writer's *last* write to precede the in-flight export's stamp:

1. `10:00:00.1` — plugin-spawned `wiki db autosync` starts `export_knowledge`;
   `sources` is scanned early (second in `SYNC_TABLES`, `db_sync.py:38-39`).
2. `10:00:01` — a *short* mutation commits (e.g. a `wiki sources rm` tombstone, or
   an MCP/worker single-row write) and finishes.
3. `10:00:01.6` — that process's `maybe_auto_export` sees the **old**
   `last_export_ts`, so its gate is open and it starts its own export.
4. `10:00:02` — export #2 finishes and `os.replace`s a *correct* snapshot.
5. `10:00:03` — the slower export #1 finishes and `os.replace`s its **stale**
   snapshot over it, then stamps `last_export_ts = 10:00:03Z`.
6. Gate is now `10:00:01Z >= 10:00:03Z` → `False`. The row is in neither the
   published file nor any future export until an unrelated later mutation.

A second, simpler variant needs no overlap at all: any writer whose own export
hook *fails* (best-effort — §13.1: "an export failure is printed but never breaks
the host command"; CAND-03's EXDEV is one such failure) has its row permanently
gated shut by another process's later stamp.

**Test check.** `test_db_autosync.py` exercises the gate only single-threaded
(e.g. `assert res2.exported is None` at line 740). No concurrency test exists.

**Severity.** P2 stands — silent degradation with a workaround (any later
mutation, or an explicit re-export). Not P1: it is a race, not a deterministic
break, and it self-heals on the next local write.

---

### sync_db-4 — DOWNGRADED to P3

The mechanism is real; the framing, both spec references, and the stated
consequences are all overstated. Three separate problems:

**(i) "non-atomic" is wrong.** `write_sync_state` (`db_sync.py:656-666`) writes a
unique temp sibling and `os.replace`s it. `os.replace` **is** atomic — no reader
can ever observe a torn file. The real defect is that the *read-modify-write* is
unserialized (a lost update) and that there is no `fsync` before the replace
(a power-loss durability gap). Calling it "non-atomic" will send an implementer
after the wrong bug.

**(ii) The §11.1 reference does not cover this file.** I read
SYSTEM_BEHAVIOR.md:775-785. The locking mandate is scoped explicitly:
"**Global and project config mutations** MUST hold a per-target process/file lock
across read/merge/write…" and the following paragraph is about `save_config()`.
Nothing in §11.1 extends the mandate to `sync_state.json`. The proposal's claim
that "§11.1 mandates locked read/merge/write for durable local state" is a
generalization the spec does not make.

**(iii) The §13.3 reference is scoped to the read path, and the code already
complies.** SYSTEM_BEHAVIOR.md:1332-1337 reads: "**If the file exists but cannot
be read, decoded, or validated** … Corruption must never be converted to `{}` and
must never generate a replacement identity or discard peer high-water marks."
That sentence governs the corrupt/unreadable-file case, which
`read_sync_state`/`_validate_sync_state` (`db_sync.py:597-653`) handles correctly —
the inspector concedes this. A lost update from a concurrent RMW is a different
mechanism the spec does not address; citing §13.3 as a violated contract is a
misread.

**Consequences are idempotent and self-limiting.** I traced each:

- *Split identity.* The orphan `dev-<idB>.jsonl` is imported as a peer, but
  `import_all_peers` checkpoints by `export_id` (`db_sync.py:1594-1605`), so it is
  imported **once** and then skipped forever — not "re-imported forever". Its
  content is this device's own rows, which are content-idempotent under LWW. Net
  damage: one redundant import plus an inflated device count in the dashboard.
  Cosmetic, not corrupting.
- *Lost high-water marks.* Reverting a `last_export_ts` causes one redundant
  export (§13.1 explicitly accepts redundant exports as idempotent and
  self-terminating). Reverting `peers[...]["last_export_id"]` causes a redundant
  re-import, also content-idempotent. Neither loses data.
- The race window for `get_device_id` exists only on a device that has never run
  any sync command — a one-time sub-second window on first use.

**The author already fixed the in-process half.** `db_sync.py:1568-1571` carries an
explicit comment: "Initialize identity before taking the mutable state snapshot.
Otherwise a first-run `_peer_files()` call can persist an id after `state` was read
as `{}` …". So the ordering hazard is known and handled intra-process; only the
cross-process case remains.

**Verdict: downgraded to P3** (hygiene/robustness gap: unserialized RMW, missing
fsync, and a §11.1-style locking primitive that exists but is not applied here).
It should still be fixed — it is cheap — but it is not a contract violation and
causes no data loss, so it does not clear the P2 bar.

---

### sync_db-5 — DOWNGRADED to P3

**Code re-verified and confirmed.** `db_sync.py:1362-1371` really does
`return "skipped"` on `remote_ts <= local_ts` with no payload comparison, while
`db_sync.py:1377-1390` gives immutable rows the canonical-JSON tie-break. The
asymmetry is real, and `_lw_upsert_source:1306-1307` has the same shape.

**But there is no contract violation — the spec says exactly this.** I read
SYSTEM_BEHAVIOR.md §13.1 at lines 1250-1256:

> "A row with the same key and equal/older LWW revision is `skipped`, not
> rewritten or counted as updated. Immutable rows without a revision clock compare
> full row content; equal content is skipped, while a malformed same-key
> disagreement uses a deterministic canonical-payload tie-break so both peers
> converge instead of alternating."

The tie-break is deliberately scoped to the *immutable, no-revision-clock* case.
Code conforms to spec exactly. Arena rule 5 makes spec-vs-code **divergence** a
finding; there is no divergence here. This is a design gap in the spec, which is a
different (and lower-priority) class than the other four items.

**"Ties are not exotic" is the weak leg, and I do not accept it.** The claim needs
two devices to write **different payloads to the same already-shared row id inside
the same wall-clock second**. Two independent constraints bite:

- The id must already be shared. New rows get fresh `_new_id()` UUIDs per device
  (`db/_entities.py:34-36`), so an independent build on each device produces
  *different* ids — which lands in sync_db-1's territory, not here.
- Only `_now_iso()`-stamped tables are second-precision. `sources` is not one of
  them: the `sources_touch_updated_at` trigger uses
  `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` (`db/schema.py:731-736`) — **millisecond**
  precision — and the same holds for `compiler_generations`. So the largest and
  most frequently mutated synchronized table is not exposed at all, contrary to the
  proposal's inclusion of `_lw_upsert_source` in the same breath.

**"Diverges permanently" is also overstated.** The skip is sticky only while
*neither* replica ever touches the row again. Any subsequent edit on either device
advances `updated_at` past the tie and the row converges on the next pass. So the
divergence window is "until the next edit of that specific row", not "forever".

**Test check.** No test constructs an equal-timestamp/unequal-payload mutable row;
the immutable tie-break is exercised indirectly by
`test_equivalent_composite_rows_do_not_ping_pong` (`test_db_autosync.py:742+`),
which pins the *equal-content* path only.

**Verdict: downgraded to P3.** Real latent convergence hole worth a docs-first fix,
but it is a spec design gap rather than a violated contract, its reachability is
much narrower than argued, and it is self-healing. It should ride along with
sync_db-1's merge-policy work (which is what actually makes shared ids common
enough for ties to matter), not compete with it for batch priority.

---

## 2. Suggested Alternatives

### For sync_db-1 (highest value — split it into two shippable halves)

1. **Half A (no policy decision needed, ship first).** Change `_do_insert` to
   `return conn.execute(...).rowcount` and make `_lw_upsert` /
   `_lw_upsert_source` branch on it. A swallowed insert must become an explicit
   third outcome — `"conflicted"` — carried on a new `ImportStats.conflicted`
   counter and surfaced in the autosync report (§32: never report a failed
   operation as success). Simultaneously, make `import_all_peers` catch a
   per-file failure, record it in the result, and **continue to the next peer**,
   writing `write_sync_state` in a `finally` so successful peers keep their
   checkpoints. This alone converts sync_db-1(b) from a permanent
   whole-chain wedge into a single reported bad peer file.
2. **Half B (needs the Master Plan's locked-decision section).** Per synchronized
   secondary UNIQUE index, declare the merge rule and implement remote-id →
   local-id remapping the way `sources` already does for `sync_key`:
   - `graph_entities` on `(canonical_name, entity_type)` → identity-merge, then
     rewrite the peer's `graph_relations.source_entity_id`/`target_entity_id`,
     `graph_relation_supports`, `entity_aliases.entity_id`,
     `entity_merge_proposals`, and `entity_resolution_lineage` through the map;
   - `source_spans` on `(source_id, content_hash)` → identity-merge, then rewrite
     `claim_supports.source_span_id` and the JSON `source_span_ids` lists on
     `graph_entities`/`knowledge_units`;
   - `entity_aliases` on the partial index → merge or report; it carries no
     inbound references, so skip-and-report is acceptable.
   **This is the part that must not be hot-patched:** an id-remap that misses one
   referencing column silently produces a second generation of dangling rows.
3. **Fix the root of sub-case (b) too, not just its symptom.** The wedge exists
   because `sync_key` is set only `AFTER INSERT` while two paths mutate `relpath`
   afterwards (`source_tools.py:378`, `ingest_raw.py:2267`). Decide explicitly
   whether `sync_key` is (i) an immutable birth identity — then the import must
   merge on `relpath` as a documented fallback before inserting — or (ii) a
   derived mirror of `relpath` — then add an `AFTER UPDATE OF relpath` trigger and
   a migration. Either way SCHEMA §11.17 must state which, because today it is
   neither.
4. Regression tests to write: (a) two devices, same file, distinct `SPAN-` ids →
   after import `SELECT COUNT(*) FROM claim_supports WHERE source_span_id NOT IN
   (SELECT id FROM source_spans)` must be `0`; (b) two devices, same
   `(canonical_name, entity_type)`, distinct `ENT-` ids → no orphan
   `graph_relations`; (c) `stats.inserted` must never exceed the rows actually
   present after the pass; (d) a peer whose `sources` row conflicts on `relpath`
   must be reported and the *next* peer file must still import and checkpoint.

### For sync_db-2

Beyond the inspector's fix, the durable cure is to delete the duplication
outright: keep **one** `_TRIGGER_BODIES: dict[str, str]` mapping, have `SCHEMA_SQL`
composition and `_refresh_current_triggers` both render from it, and rewrite
`_triggers_need_refresh` to compare `sqlite_master.sql` against the same rendered
body after whitespace normalization (`" ".join(sql.split())`). Then drift is
impossible by construction and the allowlist disappears. Use a raw string
(`r"""…"""`) or `char(92)` for the separator so no future escape can eat it.
Add a `ruff`-visible test that asserts `"replace(NEW.relpath, '\\\\', '/')"` is
present in the *installed* trigger of a `connect()`-created DB — not in the
constant, which is what makes the current bug invisible.

### For sync_db-3

Prefer capturing the stamp in `export_for_device` **before** the call rather than
threading it out of `ExportStats`:

```python
started = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
export_knowledge(db_path, out)
state = read_sync_state(internal_dir)
state["last_export_ts"] = started
write_sync_state(internal_dir, state)
```

This is a two-line change with no cross-module contract, and it is strictly safe:
the worst case is one extra idempotent re-export, which §13.1 already blesses.
Threading a value out of `ExportStats` widens a public return type for no gain.
Additionally close the stale-overwrite half of step 5 above: `export_knowledge`
should skip the `os.replace` if the target's `export_id` is newer than the one it
started with, or the whole export should hold the same lock proposed for
sync_db-4. Test with a monkeypatched clock plus a writer injected between the
`sources` scan and the stamp.

### For sync_db-4 (as a P3)

Do the cheap correct thing rather than the elaborate one: wrap `get_device_id`,
`export_for_device`'s stamp, and `import_all_peers`' checkpoint write in a single
`durable_io.locked_path(state_path)` held for the whole `autosync` pass, always
re-reading state *inside* the lock, and route the write through
`durable_io.atomic_write_text` (which also gives the missing flush). Doing this at
the `autosync` granularity fixes the identity race, the lost update, and the
overlapping-export half of sync_db-3 in one change — which is a strong argument for
batching -3 and -4 together despite -4's lower severity. **Also file the Windows
gap separately**: `durable_io.py:23` degrades `locked_path` to a `threading.RLock`
on `nt`, so this fix is a no-op cross-process on Windows; that needs a product
decision, not a silent partial fix.

### For sync_db-5 (as a P3)

Sequence it *after* sync_db-1's identity merge, since that is what makes shared row
ids common enough for ties to matter. Then, docs-first, amend SYSTEM_BEHAVIOR §13.1
to extend the canonical-payload tie-break to mutable rows on an exact-timestamp
disagreement, counted as a distinct `tie_broken` statistic (§32 observability), and
only then change `_lw_upsert`. Raising `_now_iso()` to millisecond precision (to
match what `sources_touch_updated_at` already does at `db/schema.py:731-736`) is
the cheaper 80% and can ship independently — but it is a probability reduction, not
a convergence guarantee, and the spec text must not pretend otherwise.

### Cross-cutting note on the proposal's "What I could NOT verify" section

The Unicode-normalization concern parked there is **partly already handled**:
`db/_entities.py:39-40` defines `_portable_graph_source_key` with an explicit
`unicodedata.normalize("NFC", ...)`. Before filing it as a new finding, check
whether `relpath`/`wiki_path` reach `sync_key` and the `source_pages` tombstone
token through that helper or bypass it — the answer changes it from a defect to a
non-issue, and it is one grep.

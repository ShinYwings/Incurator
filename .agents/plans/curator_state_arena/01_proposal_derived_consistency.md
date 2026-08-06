# Inspector Report: `derived_consistency` (Observations D and E)

Date: 2026-08-06 | master @ `02faa0a` (v0.46.0) | Method: read-only measurement
per `00_problem.md`. No code, docs, config, vault, or DB was modified. The live
DB was opened only via `sqlite3 "file:...state.sqlite?mode=ro"` / Python
`sqlite3.connect(..., uri=True)` against the `?mode=ro` URI. This report was
written after reading `01_proposal_storage_topology.md` in full to avoid
re-deriving its Observation-A findings; where this report depends on the same
commit history (`6556fc5` → `f8b40be`), it cites that report and extends it to
a different set of files (`sync-report.json`, `log.md`, `runtime/*.json`) and a
different consumer (the plugin chat sidebar) that Observation A's report does
not touch.

## 0. Charter recap

Per-artifact question: for each of `Collections/`, `index.md`, `overview.md`,
`runtime/sources.json`, `runtime/status.json`, `runtime/jobs.json`, `log.md`,
`ledger.md`, `sync-report.json`, `sync_state.json` — who writes it, when, and
is it ever read back as **input** (not just display)? Plus: `overview.md`
(120 KB) / `index.md` (60 KB) scaling, and the "1372 vs 1371" drift class
beyond the already-filed orphan `CTX-f349d7bf`.

## 1. Writer map (measured from source, not docs)

| artifact | resolves to (code) | writer(s) | trigger |
|---|---|---|---|
| `index.md` | `paths.internal / "index.md"` (`config.py:160-163`) | `page_writer.rebuild_index` (`page_writer.py:323-354`) | every `wiki add`, `wiki build --wait`/worker L3 pass, `wiki sync`, `wiki lint --refresh-manifests` |
| `overview.md` | `paths.internal / "overview.md"` (`config.py:155-158`) | `ingest_llm._update_overview` (`ingest_llm.py:384-477`) | every `wiki add`/`wiki build --wait`/worker L3 pass, `wiki lint --refresh-manifests` — **NOT** `wiki sync` (§F4) |
| `ledger.md` | `paths.internal / "ledger.md"` (`config.py:170-173`) | `ingest_llm._update_ledger` (`ingest_llm.py:342-381`) | same as `overview.md` — **NOT** `wiki sync` (§F4) |
| `log.md` (`paths.log`) | `paths.event_log` = `machine_cache / "log.md"` (`config.py:165-168` → `114-116`) | `page_writer.append_log_entry` (`page_writer.py:362-432`) | `wiki add` **only if `concept_ids` truthy** (`ingest_llm.py:573-577`), `wiki sync` (unconditional, `sync.py:1081-1087`), `wiki lint --refresh-manifests` (unconditional) |
| `Collections/*` | `paths.contexts/atoms/concepts/synthesis` | `pipeline/compile.py`, `pipeline/synthesis.py` | per-source/global compile, every add/build |
| `runtime/status.json`, `sources.json`, `jobs.json` | `machine_cache / "runtime" / "<name>.json"` (`config.py:102-104`) | `runtime_state.write_runtime_snapshots` (`runtime_state.py:430-438`) | every `wiki add`/`build`/`lint`/`sources`/`jobs`/`config` mutation, ingest worker heartbeats |
| `sync-report.json` | `machine_cache / "sync-report.json"` (`config.py:110-112`) | `commands/common.py:_write_latest_sync_report` (:423-467) | only via `_run_sync_report_only` (called from **synchronous** `wiki add`/`wiki build --wait`) or `wiki sync` itself — **never** from the background worker (§F3) |
| `sync_state.json` | `get_global_config_dir() / "sync_state" / "<vault_key>.json"` (`db_sync.py:589-594`) | `db_sync.write_sync_state` | device-local sync/export bookkeeping — Observation-C territory, out of my scope beyond noting it shares the same `machine_cache`-adjacent global-cache-dir pattern as `sync-report.json`/`log.md` |

Two things fall out of this table immediately and drive every finding below:

1. **`log.md` and `sync-report.json` do not live where `index.md`/`overview.md`/
   `ledger.md` live.** The latter three are `paths.internal / "<name>"` —
   physically inside `<vault>/.curator/`. The former two are
   `paths.machine_cache / "<name>"` — physically inside
   `<repo>/.cache/vaults/<hash>/`, **outside the vault entirely**. This single
   fact explains Observation E's exact staleness pattern and is the seed of
   F1/F2 below.
2. **`overview.md`/`ledger.md` are never touched by `wiki sync`**, despite its
   own docstring and CLI success message claiming otherwise (F4).

## 2. Finding F1 — [P1] Chat sidebar status indicator has read from a dead file for over a month; the bug is silent (try/catch swallows it) and polls every 2s

**Measurement.** `plugin/src/ui/chat/ChatSidebarView.ts:465-491`:

```ts
private updateStatusBar(): void {
  if (!this.statusBarEl) return;
  try {
    const vaultRoot = (this.plugin.app.vault.adapter as any).getBasePath?.() || "";
    if (!vaultRoot) return;
    const jobsPath = join(vaultRoot, ".curator", "runtime", "jobs.json");
    const statusPath = join(vaultRoot, ".curator", "runtime", "status.json");
    ...
    if (existsSync(jobsPath)) {
      const raw = readFileSync(jobsPath, "utf8");
      const data = JSON.parse(raw);
      if (data.running && data.running.length > 0) { /* show spinner "N running" */ }
      else if (data.queued && data.queued.length > 0) { /* show spinner "N queued" */ }
    }
  } catch (e) { /* fail silently */ }
}
```
wired at `:254-255` (`this.statusPollInterval = setInterval(() => this.updateStatusBar(), 2000)`)
inside the view's open lifecycle — this runs every 2 seconds for the entire
time the chat sidebar is open.

This reads `<vaultRoot>/.curator/runtime/jobs.json` — a **vault-relative**
path. But per §1 and `config.py:102-104`, the backend has written
`runtime/*.json` to `machine_cache` (`<repo>/.cache/vaults/<hash>/runtime/`)
since commit `6556fc5` (2026-07-06, per `01_proposal_storage_topology.md §2`).
I confirmed this is not a theoretical mismatch by diffing the two files
directly:

```
$ cat second_brain/.curator/runtime/jobs.json | head
{
  "ok": true,
  "generated_at": "2026-07-04T04:08:41Z",
  "running": [],
  "queued": [],
  "done": [],
  "failed": [{ "job_id": 36, "source_id": 27,
    "source_name": "Multiple_View_Geometry_in_Computer_Vision-EN.md",
    "job_type": "l2_atoms", "state": "failed", ... }]
}

$ cat .cache/vaults/13ed51f8b06cb88e/runtime/jobs.json | head
{
  "ok": true,
  "generated_at": "2026-08-05T12:12:40Z",
  "running": [{ "job_id": 40, "source_id": 37,
    "source_name": "3D Line Mapping Revisited2023 - Liu et al. - .md",
    "job_type": "l2_atoms", "state": "running", "phase": "l3_concepts",
    "progress": 0.75, ... }],
  "queued": [ ... ]
}
```

The vault-side file (`ChatSidebarView.ts`'s actual read target) is frozen at
**2026-07-04T04:08:41Z** — `running: []`, `queued: []`, forever — while the
real, currently-written file shows an **actively running** job as of
2026-08-05. `existsSync(jobsPath)` is always `true` (the stale file exists,
it's just never updated), so the code silently reads plausible-but-dead JSON
instead of failing loudly. This is a direct instance of the brief's key
question — "read back as INPUT... staleness causes wrong behaviour, not just
stale display" — because the status bar's entire function is a live indicator
consumed by the user to answer "is something happening right now," and it has
been giving the wrong answer (always "nothing running") continuously since
2026-07-06.

**Contrast with the sibling dashboard**, which explicitly engineered around
this exact class of bug — `incuratorDashboardModal.ts:203-210`:
```ts
/**
 * Fetch the live `wiki status --json` payload (status + sources + jobs),
 * memoized for the current render. The dashboard reads ALL backend info from
 * this — never from the on-disk snapshot file — so it can never show stale
 * data left behind when a backend change forgets to regenerate the snapshot.
 */
```
`fetchLiveStatus()` (`:211-233`) shells out to `wiki status --json` live and
never touches the on-disk `runtime/*.json` directly. `ChatSidebarView.ts`'s
`updateStatusBar` was never brought in line with this pattern — it predates
or was simply never updated after the July 6 relocation.

**Spec contract, quoted** — `docs/specs/plugin_schema/PLUGIN_SCHEMA.md:67-73`:
> The plugin may write `.cache/config/devices.json` as the single exception to
> the `.curator/` write boundary... The plugin may also read repo-cache
> `runtime/*.json` dashboard snapshots, but backend code is the only writer
> for those files.

The spec itself calls these "**repo-cache** `runtime/*.json`" — i.e. outside
the vault. `ChatSidebarView.ts` reading `<vaultRoot>/.curator/runtime/...` is
not an ambiguous edge case, it is reading a path the spec says does not hold
the authoritative file.

**Cross-check against tests (Ground Rule 4).** No test file
`ChatSidebarView.test.ts` exists (`find plugin -iname "ChatSidebarView*"`
returns only the source file). No `*.test.ts` anywhere references
`updateStatusBar`, `statusBarEl`, or a `runtime.*jobs\.json` pattern. Nothing
pins this as intentional; it is untested, unpinned dead code.

**Failure scenario.** A user runs `wiki build` (default, queued to the
background worker — the documented default path) on a large batch of PDFs,
then opens the Obsidian chat sidebar to ask a question while ingestion is
still running. The status bar shows nothing (no spinner, no "N running"),
because it is reading July 4th's `jobs.json` where `running: []`. The user has
no way to tell from the chat UI that ingestion is in progress, and no
workaround exists short of running `wiki status` in a terminal or opening the
separate dashboard modal (which does query live).

**Minor associated nit**, same block: `statusPath` (`:471`) is computed but
never read anywhere in the function — dead local variable, consistent with
this code path having been abandoned mid-refactor rather than actively
maintained.

## 3. Finding F2 — [P2] The July 6 relocation only ever migrated `state.sqlite`; `sync-report.json`, `log.md`, and `runtime/*.json` were never migrated, are now permanently orphaned at their old vault-side path, and the migration capability that could have caught this was deleted one day later

**Measurement.** `01_proposal_storage_topology.md §2` already establishes the
commit pair for `state.sqlite`: `6556fc5` (2026-07-06, "relocate device-local
state to repo cache") introduced the one-time migration, `f8b40be`
(2026-07-07) deleted it entirely one day later. I re-read the same diff
(`git show 6556fc5 -- backend/src/curator/config.py`) specifically for what
`prepare_machine_state()` migrated, and it is narrower than the commit
message claims:

> commit message: *"A one-time migration moves existing `.curator/state.sqlite`
> **and sidecars** to the new location..."*

but the actual body:
```python
def prepare_machine_state(paths: WikiPaths) -> None:
    ...
    old_db = paths.internal / consts.STATE_DB
    new_db = paths.state_db
    if old_db.exists() and new_db.exists():
        raise RuntimeError(...)
    if not old_db.exists():
        return
    ...
    for suffix in ("", "-wal", "-shm"):
        source = old_db.with_name(old_db.name + suffix)
        if not source.exists():
            continue
        shutil.copy2(source, backup_dir / source.name)
        shutil.move(str(source), str(new_db.with_name(new_db.name + suffix)))
```
only ever touches `old_db` = `.curator/state.sqlite` (+ `-wal`/`-shm`). It
never references `paths.internal / "sync-report.json"`, `paths.internal /
"log.md"`, or `paths.internal / "runtime"`. "And sidecars" in the commit
message was never implemented for anything but the DB's own WAL/SHM files.
Because `f8b40be` deleted this function's body entirely one day later
(confirmed: `git show f8b40be -- backend/src/curator/config.py` shows the
whole migration block removed, leaving only `mkdir` + `vault_root` marker
write), **there has never been, and can never again be without new code, any
migration path for these three files.** This is stronger than "not yet
migrated" — the capability to migrate them was added and removed in the same
72-hour window without ever covering them.

I confirmed the resulting fossils directly:

```
$ ls -la second_brain/.curator/sync-report.json second_brain/.curator/log.md
-rw-r--r--  100352  Jul  2 ...  sync-report.json
-rw-r--r--   ...    Jul  2 ...  log.md

$ ls -la second_brain/.curator/runtime/
jobs.json     4841 bytes   Jul  4 13:08
sources.json 20641 bytes   Jul  4 13:08
status.json   4717 bytes   Jul  4 13:08

$ ls -la .cache/vaults/13ed51f8b06cb88e/{log.md,sync-report.json}
log.md            10711 bytes  Aug  5 21:36   # live, actively appended
sync-report.json    310 bytes  Jul  9 11:45   # live, but see F3
```

The vault-side `log.md` and `sync-report.json` are not merely stale — they
are a **different file with different content and a different size** than the
one any current code path will ever write to again (100 KB fossil vs. 310-byte
live file for `sync-report.json`; both named identically, sitting one
directory apart). The `runtime/*.json` fossils are all dated **2026-07-04
13:08**, one day before the July 6 relocation commit — i.e. the last moment
any `wiki` command in this vault ran against pre-relocation code, exactly as
the mechanism predicts.

**Spec contradiction, quoted.** `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:919-926`:
> Backend code is the single writer for repo-cache `runtime/*.json`.
> The plugin may read these files directly through the Obsidian vault adapter
> only after giving the local backend a chance to refresh them.
> ...
> Runtime snapshots must be derived from backend-owned state (`state.sqlite`,
> internal search metadata, job queue, config) and must not become a second
> source of truth.

This is self-contradictory as written, independent of F1: it calls the files
"**repo-cache** `runtime/*.json`" (outside the vault, per `config.py:102-104`
and confirmed above) in the same breath as saying "the plugin may read these
files directly through **the Obsidian vault adapter**" — the Obsidian vault
adapter is sandboxed to the vault directory and cannot read
`<repo>/.cache/...` at all. Whichever half is correct, the vault-side
`.curator/runtime/` fossil (§ above) is exactly the kind of "second source of
truth" this paragraph says must not exist, and it currently does, permanently,
with no writer and no reconciler.

**Failure scenario.** Beyond F1 (which is the direct, currently-active
consequence): any future plugin feature, script, or human that inspects
`<vault>/.curator/{log.md,sync-report.json,runtime/}` — the paths CLAUDE.md's
own "Vault Structure" tree and `SYSTEM_BEHAVIOR.md §22.3` both still document
(per `01_proposal_storage_topology.md` F4, same root cause, different files) —
will read confidently-formatted, schema-valid, but 5-week-stale data with no
signal that it is dead. A backup/restore of `second_brain/` (e.g. via
Syncthing, which `01_proposal_storage_topology.md` F5 confirms is genuinely
active on this vault) faithfully preserves these fossils forever, since
nothing ever deletes them either.

## 4. Finding F3 — [P2] Even at its correct (post-migration) location, `sync-report.json` silently goes stale under the documented default workflow, because the writer is only reachable from synchronous CLI paths, never from the background worker

**Measurement.** `commands/common.py:_write_latest_sync_report` (:423-467) is
the sole writer. Its only callers, found by exhaustive grep of
`backend/src/curator` for `_write_latest_sync_report` /
`_run_sync_report_only`:

- `commands/common.py:661` — inside `_run_sync_report_only` (:579-690), whose
  own docstring says *"Run the default sync repair loop after add/curate/query."*
- `commands/core.py:1274` — inside the `sync()` Typer command body, guarded by
  `if not dry_run:`.

`_run_sync_report_only` itself is called from exactly two places:
- `commands/core.py:767-768`, inside `add()`, guarded by
  `if summarized > 0: ... if not no_sync: _run_sync_report_only(...)`.
- `commands/core.py:889-890`, inside `build()`, but **only inside the
  synchronous `--wait` branch** (`commands/core.py:852-897`).

`build()`'s **default** branch (no `--wait`, `commands/core.py:840-850`) does:
```python
if not wait:
    from .. import ingest_worker
    job_ids = ingest_worker.enqueue_l2_l3_for_sources(paths, source_ids, trigger="wiki_build")
    console.print()
    _ok(f"Queued {len(job_ids)} L2/L3 job(s).")
    _spawn_background_worker(paths)
    return
```
— enqueues and returns immediately, with **no call to `_run_sync_report_only`
or `_invalidate_latest_sync_report` at all**. I confirmed by grepping
`backend/src/curator/ingest_worker.py` for `sync_report`,
`_write_latest_sync_report`, `finalize_routing_tables`, `append_log_entry`,
`_update_ledger`, `_update_overview`, and `rebuild_index` — **zero matches**.
The worker does call `ingest_llm.run_l3_from_existing_atoms`
(`ingest_worker.py:158,220`), which is why `index.md`/`ledger.md`/`overview.md`
stay fresh under the worker path (§1) — but nothing in that call chain ever
touches `sync-report.json`.

This vault demonstrably uses the worker path: the live `runtime/jobs.json`
(§F1) shows `job_id: 40` with `state: "running"`, `job_type: "l2_atoms"` — a
worker-processed job, not a synchronous `--wait` run. Consistent with that,
the live `sync-report.json` is dated **2026-07-09T...** (310 bytes) —
**28 days stale** relative to the 2026-08-06 "today," even though it lives at
the structurally-correct `machine_cache` path and is not touched by the F2
orphaning bug at all. This is a second, independent staleness mechanism for
the same file.

**Consumer check (the brief's key question).** The only reader is
`commands/common.py:_load_latest_sync_report` (:468-476), whose only caller is
`_render_latest_sync_report_summary` (:500-546), whose only caller is
`wiki status` (`commands/core.py:525`). This is **display-only** — the
rendered "Latest Sync Report" table in `wiki status` is not consulted by any
other command's control flow (confirmed: grep for `_load_latest_sync_report`
across `backend/src/curator` returns only this one call site). So unlike F1,
this does not currently cross from "stale display" into "wrong behaviour" —
but it is actively misleading: `wiki status` will show `health: <whatever it
was on Jul 9>` — plausibly `"clean"` — as if it reflects the vault's current
verification state, with no "N days stale" indicator, while 28 days and
(per Observation D's own numbers) hundreds of new nodes have since been added
unverified by any `wiki sync` pass.

**Failure scenario.** An operator who exclusively uses the documented default
(`wiki add` then `wiki build`, no `--wait`, relying on the background worker —
exactly what `commands/core.py:790-795`'s own docstring recommends: *"By
default the work is queued to the background worker... use --wait to run it
synchronously"*) will never see `sync-report.json` refresh, ever, no matter
how long they keep adding sources — the CLI's own recommended workflow
structurally excludes the one artifact meant to summarize verification
health.

## 5. Finding F4 — [P2] `wiki sync`'s own success message is false: it claims to rebuild `ledger.md` and `overview.md`, but the function it calls only touches `index.md` and `log.md`

**Measurement.** `sync.py:1077-1087`:
```python
def finalize_routing_tables(paths: cfg.WikiPaths) -> None:
    """Rebuild index.md, ledger.md, log.md, and overview.md."""
    today = page_writer.today_iso()
    page_writer.rebuild_index(paths, today)
    page_writer.append_log_entry(
        paths, today, "sync", "Deductive verification pass",
        ["Routing tables rebuilt by wiki sync"],
    )
```
The docstring names four files; the body calls exactly two functions
(`rebuild_index`, `append_log_entry`). There is no call to
`ingest_llm._update_ledger` or `ingest_llm._update_overview` anywhere in
`sync.py` — confirmed by grepping the file for both names (zero matches) and
by the full call-site enumeration in §1/§4 above, where the only callers of
`_update_ledger`/`_update_overview` are `ingest_llm.py:578-579,624-625` (the
add/build pipeline) and `commands/core.py:1582-1583` (`wiki lint
--refresh-manifests`, an opt-in flag).

The lie compounds at the call site — `commands/core.py:1309-1313`:
```python
if not dry_run:
    sync_module.update_all_page_hashes(paths)
    sync_module.finalize_routing_tables(paths)
    _ok("Routing tables rebuilt (index.md, ledger.md, log.md, overview.md).")
```
The success message printed to the operator explicitly names all four files
as rebuilt. Two of them were not touched by this invocation.

**Why this matters in practice, distinct from F3.** In this vault, `ledger.md`
and `overview.md` happen to stay fresh anyway, because `wiki add`/`wiki build`
(the add/build pipeline, not `wiki sync`) independently refreshes them on
every run (§1). But that is incidental to this bug, not a mitigation of it:
a vault whose L1-L3 pipeline has finished (no more new sources to add/build)
and whose only ongoing maintenance is periodic `wiki sync` — exactly the
steady-state usage `wiki sync`'s own docstring markets it for ("Run deductive
verification and rebuild routing tables") — would have `ledger.md` and
`overview.md` frozen at whatever the last `wiki add`/`build` left them,
forever, while every `wiki sync` run prints a confident "Routing tables
rebuilt (index.md, ledger.md, log.md, overview.md)" regardless.

**Failure scenario.** A future correction to `ledger.md`'s HITL stats or
`overview.md`'s domain manifest (e.g. a manual DB correction followed by
`wiki sync` to "refresh everything," which is precisely what the CLI message
tells the operator just happened) silently does not happen. The operator has
no reason to doubt the printed confirmation and no diff/hash check surfaces
the gap — `ledger.md`'s own `updated:` frontmatter timestamp (written by
`_update_ledger`, `ingest_llm.py:360`) is the only tell, and nothing prompts
anyone to check it against "when did I last run `wiki sync`."

## 6. Finding F5 — [P2] `overview.md`/`index.md` are unconditionally re-read-and-rewritten in full on every single ingest call, regardless of how much changed; cost is O(total nodes) per call, not O(delta) — confirmed against the live 1372-node corpus

**Measurement — current size and shape.**
```
$ ls -la second_brain/.curator/{overview.md,index.md,ledger.md}
overview.md  119730 bytes   updated: 2026-08-05T12:36:57Z
index.md      57736 bytes   (same run)
ledger.md        400 bytes  updated: 2026-08-05T12:36:56Z
$ wc -l overview.md index.md
1406  overview.md
1406  index.md
```
(1-second apart timestamps on `ledger.md`/`overview.md` confirm they are
written back-to-back inside one `_update_ledger()`→`_update_overview()` call,
consistent with `ingest_llm.py:578-579`.) Against the 1372-node corpus this is
**~87 bytes/node** for `overview.md` and **~42 bytes/node** for `index.md`,
both close to linear (each node contributes one bullet line plus, for
`overview.md`, a `frontmatter.summary` string capped implicitly by whatever
the LLM wrote).

**Measurement — the regeneration is unconditional and whole-corpus, every
call.** `page_writer.rebuild_index` (`page_writer.py:323-354`) calls
`_list_pages_in` (`:305-320`) once per layer:
```python
def _list_pages_in(directory: Path) -> list[tuple[str, str]]:
    if not directory.exists():
        return []
    out = []
    for page_path in sorted(directory.glob("*.md")):
        if page_path.name.startswith("."):
            continue
        parsed = read_page(page_path)   # full file read + frontmatter parse
        ...
    return out
```
— every `.md` file in every layer is opened, read, and YAML-frontmatter-parsed
on **every** call, not just files created since the last call. `_update_ledger`
(`ingest_llm.py:342-381`) recomputes counts via `sum(1 for _ in
paths.contexts.glob("*.md"))` (cheap, but still O(n) directory scan) for all
four layers plus one DB query. `_update_overview` (`ingest_llm.py:384-477`) is
the most expensive: `_read_layer` (`:387-410`) does the same full
read-and-parse as `_list_pages_in` for all four layers, **and then** a
**second, independent full scan of every L1 Context file** for the domain
histogram:
```python
domains: dict[str, int] = {}
for md in sorted((paths.contexts.glob("*.md") if paths.contexts.exists() else [])):
    if md.name.startswith("."):
        continue
    parsed = page_writer.read_page(md)   # every CTX file parsed AGAIN
    if parsed:
        d = parsed.frontmatter.get("domain", "").strip()
        ...
```
So `paths.contexts` is fully read-and-parsed **twice** per `_update_overview`
call (once inside `_read_layer(paths.contexts)`, once again for domains),
while `paths.atoms`/`concepts`/`synthesis` are read once each. None of this is
cached, diffed, or fingerprinted against the previous run — there is no
"only touch nodes changed since timestamp X" path anywhere in `rebuild_index`,
`_update_ledger`, or `_update_overview`.

This runs on **every** `wiki add` call (`ingest_llm.py:572,578-579`, inside
`run_l1_to_l3`) and every worker-processed `wiki build` job
(`ingest_worker.py:158,220` → `run_l3_from_existing_atoms` →
`ingest_llm.py:620,624-625`) — i.e. once per source added, not once per
ingest *session*. A vault built by adding N sources one at a time (the
common `wiki add <file>` workflow CLAUDE.md itself documents) pays the **full
current corpus size** in file I/O and YAML parsing on **every single one** of
those N calls.

**Scaling answer to the brief's explicit question.** File size itself scales
linearly and is not the risk (10x nodes → ~1.2 MB `overview.md` / ~580 KB
`index.md`, well within what Obsidian/a filesystem handles). The risk is
**cumulative work**: for a vault grown by N incremental `wiki add` calls to a
final size of M nodes, total bytes-read-and-reparsed across the whole ingest
history is `Σ(node_count_at_call_i)` for i=1..N, which is `O(N·M)` in the
worst case (steady per-call growth) rather than `O(M)` — i.e. **quadratic in
the number of individual ingest operations**, not just linear in final corpus
size. At the current 1372-node/1406-line scale this is invisible (sub-second
YAML parses). At 10x node count reached via the same one-source-at-a-time
workflow, every remaining `wiki add` call re-parses ~13,700 markdown files'
frontmatter (contexts scanned twice) purely to append routing-table/manifest
entries for the 1 new source it actually processed — a per-call cost that
keeps growing for the life of the vault regardless of how small each
individual `wiki add` is.

**Consumer check.** `index.md`/`overview.md`/`ledger.md` are read by
`lint.py:156-217,422-443` as **root nodes for orphan detection** (a link
FROM `index.md` marks a page as non-orphan) — this is the one place these
three files are read back as input with behavioral consequence, but it is
read-only/informational (lint reporting), not something that mutates DB state
or blocks a pipeline stage, so I am not filing it as a separate finding.

## 7. Finding F6 — [P2, latent/dormant — 0 delta measured against the live DB right now] L3 concept-report retirement has no file-cleanup step analogous to L1's orphan sweep or L4's full wipe-and-regen; the gap is real in the code but has not yet produced observable drift in this vault

**Measurement — the code asymmetry.** Three of the four layers self-heal
their markdown against DB retirement on every normal run; L3 does not:

- **L1 (Contexts):** `pipeline/compile.py:1277-1292`, inside the reconciliation
  path, unlinks every `CTX-*.md` whose id is absent from
  `SELECT context_id FROM sources WHERE context_id IS NOT NULL` — a full
  orphan sweep, every run. (This is the mechanism behind the already-filed
  `CTX-f349d7bf` orphan — that file predates this sweep's current form or was
  produced by a run this sweep didn't cover; not re-litigated here per the
  brief's instruction.)
- **L2 (Atoms):** `pipeline/compile.py:_finalize_published_source` (:511-538)
  computes `all_source_atom_ids - live_atom_ids` for the one source just
  compiled and unlinks the stale ones, every normal per-source compile.
- **L4 (Synthesis):** `pipeline/synthesis.py:reemit_synthesis` (:178-194) is
  called **unconditionally at the end of every `generate_synthesis` call**
  (`:174`) and does a full "unlink every `SYN-*.md`, then re-emit from
  `db.list_synthesis_nodes`" pass — every run, not opt-in.
- **L3 (Concepts):** `pipeline/compile.py:compile_global_l3` (:1027-1166),
  the function that runs on **every** normal `wiki add`/`wiki build`/worker
  L3 pass, calls `db.rebuild_graph_generation` unconditionally at its top
  (`:1050`), whose own docstring (`db/_entities.py:2119-2121`) states step 5:
  *"Retire (set `retired_at`) every prior non-retired report whose
  `community_key` is absent from the rebuilt set... before synthesis consumes
  it."* This retirement is triggered by ordinary topology change (a new
  source shifting which relations are active, corroboration crossing the
  ≥1-source threshold, entity-resolution membership changes) — not an edge
  case. But the loop that follows (`:1061-1076`) only **writes** markdown for
  reports returned by `db.list_community_reports(paths.state_db)`, which
  defaults to `retired_clause = "retired_at IS NULL"`
  (`db/_entities.py:2034-2052`) — i.e. it only ever adds/overwrites current
  files. There is no unlink step for a report that just became retired in
  this same call. The only code that does clean up retired-report markdown is
  `reemit_projections` (`pipeline/compile.py:1169-1220`, full wipe of
  `paths.atoms`/`paths.concepts` then full re-emit from DB), reachable only
  via the explicit opt-in `wiki sync --reemit` flag
  (`commands/core.py:968-973,1046-1053`, default `False`) — never from the
  default `wiki add`/`wiki build`/worker path.

**Measurement — current live state (this is the honest, load-bearing part of
this finding).** I queried the read-only DB and cross-referenced against the
vault's actual `Collections/03_Concepts/` directory, replicating
`_concept_id_for_report`'s `sha256("concept:" + id)[:8]` id derivation in
Python:
```
community_reports total: 240   retired: 7   live: 233
Collections/03_Concepts/*.md count: 233
retired reports WITH a still-existing CON-*.md file: 0
retired reports WITHOUT a file (correctly absent): 7
```
And, layer by layer, files vs. DB-live counts:
```
             CTX   ATM   CON   SYN   TOTAL
files:        37  1098   233     4   1372
db-live:       36  1098   233     4   1371
delta:          1     0     0     0      1
```
**The entire 1372-vs-1371 delta is accounted for exactly by the already-filed
orphan CTX; ATM/CON/SYN currently have zero drift.** So, directly answering
the brief's "what else could produce this class of drift": right now, in this
vault, nothing else does. The L3 gap above is a real, measured code asymmetry
(three of four layers self-heal every run, one does not), and it is the kind
of mechanism that *would* reproduce Observation D's drift class the next time
a community report is retired without a `--reemit` following it — but I am
not asserting it is currently active, because my own measurement of the live
DB against the live filesystem contradicts that. I flag it at P2 rather than
higher because of that measured absence, in the same spirit as
`01_proposal_storage_topology.md`'s F6 ("not currently load-bearing, but the
mechanism... is real, measured, and un-flagged").

**Spec tension.** `docs/specs/curator_schema/SCHEMA.md:739-746`:
> The `.curator/Collections/` L1–L4 markdown pages (`CTX-`, `ATM-`, `CON-`,
> `SYN-`) are a DERIVED, disposable projection of the DB ("object code")...
> Projection pages may be deleted and re-emitted from the DB at any time.
> Because they are emitted (never edited as truth), **there is no DB↔file
> drift.**

This is stated as an absolute, mechanism-backed guarantee ("because they are
emitted... there is no drift"), but the guarantee is only actually enforced
for L1/L2/L4 by the sweep/per-source-diff/full-wipe code cited above; L3's
enforcement exists solely as an opt-in flag a normal ingest workflow never
triggers. The spec's "no drift" claim is true of this vault's current
snapshot by luck of timing, not by construction, for the L3 layer.

**Failure scenario (hypothetical, clearly labeled as such).** A vault
operator adds a new source whose relations cause an existing community's
active-relation set to change enough that `rebuild_graph_generation` assigns
it a new `community_key` (mid-topology-change — SCHEMA's own documented
trigger for retirement) and never subsequently runs `wiki sync --reemit`. The
old `CON-<hash-of-old-id>.md` file remains in `Collections/03_Concepts/`,
counted by `index.md`'s "L3 — Concepts" section, `overview.md`'s L3 count and
list, and any Obsidian-side navigation of `Collections/`, permanently, citing
a report the DB no longer serves — reproducing exactly the class of
file-count-exceeds-live-DB-count drift Observation D measured for L1, but for
L3, with no equivalent "already filed" ticket and no automatic path back to
zero short of the opt-in reemit.

## 8. Summary table

| # | Severity | Artifact(s) | One-line claim |
|---|---|---|---|
| F1 | P1 | `runtime/jobs.json` (consumer: `ChatSidebarView.ts`) | Chat sidebar status spinner reads a vault-relative path the backend stopped writing to on 2026-07-06; permanently shows "nothing running," polled every 2s, silently |
| F2 | P2 | `sync-report.json`, `log.md`, `runtime/*.json` (vault-side) | July 6 relocation migrated only `state.sqlite`; these three were never migrated, are now permanently orphaned (migration capability itself deleted one day later), directly causing F1 |
| F3 | P2 | `sync-report.json` (correct machine_cache copy) | Writer only reachable from synchronous CLI paths (`wiki add`, `wiki build --wait`, `wiki sync`), never from the background worker that the CLI's own documented default (`wiki build`, no `--wait`) uses — stale 28 days in this vault despite continuous activity |
| F4 | P2 | `ledger.md`, `overview.md` (via `wiki sync`) | `finalize_routing_tables`'s docstring and the CLI's printed success message both claim `wiki sync` rebuilds `ledger.md`/`overview.md`; the function body never calls either updater |
| F5 | P2 | `overview.md`, `index.md` | Full read-and-reparse of every node's frontmatter on every single ingest call (contexts scanned twice inside `overview.md`'s builder), no diffing — O(N·M) cumulative cost across N incremental `wiki add` calls to final size M, not O(M) |
| F6 | P2 (latent, 0 current delta measured) | `Collections/03_Concepts/` (CON-*.md) | L3 concept retirement has no per-run cleanup analogous to L1's orphan sweep or L4's full wipe-and-regen; only reachable via opt-in `wiki sync --reemit`. Measured against the live vault: currently 0 drift (233 files = 233 live reports) — the gap is real but dormant |

## 9. Cross-check against `backend/tests/` and plugin `*.test.ts`

- `backend/tests/test_reemit_projections.py` exists and (by name) covers
  `reemit_projections` — consistent with F6: the *opt-in* reconciliation path
  is tested, but I found no test that exercises `compile_global_l3`'s
  *default* path specifically asserting a retired community report's stale
  `CON-*.md` is or isn't cleaned up without `--reemit`, which is the actual
  gap F6 describes.
- `backend/tests/test_sync_report_filter.py` and
  `test_sync_layer_status_truthfulness.py` exist; neither name nor (spot-check
  via grep for `enqueue_l2_l3_for_sources`/`ingest_worker`) content asserts
  that `sync-report.json` is refreshed by the background-worker/queued
  `wiki build` path — consistent with F3 being an untested gap, not a
  contradicted one.
- No test references `finalize_routing_tables` calling `_update_ledger` or
  `_update_overview` — consistent with F4.
- No `ChatSidebarView.test.ts` exists at all — consistent with F1 being
  entirely unpinned.

None of the six findings above are contradicted by an existing test asserting
the opposite behavior — per Ground Rule 4, this means the claims stand rather
than needing to be withdrawn or sharpened against a pinned contract.

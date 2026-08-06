# Red-Team Critique: `storage_topology` F1/F2 and `derived_consistency` F1

Date: 2026-08-06 | master @ `02faa0a` (v0.46.0) | Method: read-only. DB opened
only via `?mode=ro` (never queried in this pass — all evidence here is code,
git history, and live vault filesystem state). No code, docs, config, vault,
or DB was modified; the only write is this document.

Role: adversarial. My job is to find the weakest point in each finding and
try to break it. Where a finding survives, I say so plainly — REFUTE is not
the default outcome, CONFIRMED is a legitimate verdict when the attack fails.

## Summary verdict table

| Finding | Original severity | Verdict | New severity | Why |
|---|---|---|---|---|
| STORAGE F1 (rename orphans DB) | P0 | **DOWNGRADED** | P1 | Self-heal mechanism and rename-reachability both confirmed real, but the "orphan" is not destroyed — it sits intact under the old cache key and is trivially relocatable once found. No data loss occurs. |
| STORAGE F2 (`.cache` loss = total unrecoverable loss) | P0 | **DOWNGRADED** | P1 | Self-heal confirmed real. But a working, default-on, already-in-the-vault recovery path (`.curator/sync/dev-*.jsonl` + `wiki db import`/`wiki db autosync`) recovers every table the finding calls irreplaceable (`dag_edges`, `source_spans`, `knowledge_units`, `community_reports`, entities/relations, `sources`, `atoms`, `concepts`, `synthesis_nodes`). Only `ingest_jobs`/`job_events`/`ingest_runs` (operational audit trail) and search embeddings (regenerable) are genuinely unrecoverable via this path. "Total, unrecoverable, sole source of truth destroyed" is measurably false. |
| DERIVED F1 (chat sidebar reads dead `runtime/jobs.json`) | P1 | **CONFIRMED** | P1 (stands) | Independently re-derived from source: exact same path, exact same dead-code shape, exact same mtime/content divergence. No fallback exists anywhere in the function or the class. Additional finding: the plugin has **no code path capable of computing the correct repo-cache path at all** (no sha256/vault-key logic anywhere in `plugin/src`), which changes the correct fix direction — see below. |

Both P0s survive the attack on their *mechanism* (self-heal is real, unconditional,
and undocumented) but fail the attack on their *consequence* (claimed
unrecoverable data loss). Both get redirected to a corrected, narrower P1.

---

## STORAGE F1 — [P0 claimed] Vault rename/move silently orphans the DB

### Attack 1: is the self-heal claim literally true?

Read `backend/src/curator/db/schema.py:924-944` directly (not the proposal's
excerpt):

```python
@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Context-managed connection with row factory and foreign keys enabled."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        # Self-heal for existing empty/corrupted state DB files missing base tables.
        conn.executescript(SCHEMA_SQL)
        if _triggers_need_refresh(conn):
            _refresh_current_triggers(conn)
        _stamp_schema_version(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()
```

Confirmed unconditional: `executescript(SCHEMA_SQL)` runs on **every** `connect()`
call, no existence/size guard, no try/except around it that would distinguish
"fresh empty file" from "established DB." `SCHEMA_SQL`'s statements are all
`CREATE TABLE IF NOT EXISTS` (verified via `grep -n "CREATE TABLE"
backend/src/curator/db/schema.py` — every hit is `IF NOT EXISTS`), so this is
genuinely idempotent-and-silent on a 0-byte file: SQLite accepts a zero-length
file as a trivially valid empty database (no magic-header check fails), the
`executescript` populates it with a full empty schema, and the call returns
success. **Attack fails — self-heal claim is literally true, not an
exaggeration.**

### Attack 2: is the rename scenario actually reachable?

I checked `find_wiki_root` independently (`config.py:555-576`) rather than
trusting the proposal's VAULT_ROOT-based argument:

```python
def find_wiki_root(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        cfg_file = candidate / consts.INTERNAL_DIR / consts.SETTINGS_FILE
        if cfg_file.exists():
            ...
            return candidate
    return None
```

This walks up from **cwd**, matching purely on `.curator/settings.yml`
existing — no dependency on any previously-recorded path, no `state.sqlite`
existence check. So the simplest possible reproduction is even more direct
than the proposal argued: `mv second_brain second_brain-2026 && cd
second_brain-2026 && wiki status` — no `VAULT_ROOT`, no `last_root` interaction
required at all. `get_vault_cache_dir` (`config.py:357-361`) then hashes the
new resolved path, misses the existing cache dir, and `db.connect()` self-heals
a fresh empty schema into the new location. **Attack fails — reachability is
confirmed, and simpler than the proposal's own framing.**

### Attack 3 (the one that lands): is this "data loss," or does it just look like it?

This is where F1 breaks as filed. The proposal's own severity rubric
(`00_problem.md`: *"P0 data loss/corruption or serving wrong knowledge"*)
requires actual loss or actual wrong-knowledge-serving, not merely "confusing
state exists somewhere on disk." Walk through what "orphan" concretely means:

- The old cache directory (`.cache/vaults/<old-hash>/`) is **not deleted, not
  modified, not touched at all** by the rename. `get_vault_cache_dir` only
  ever *creates* new directories; nothing in the resolve/connect path
  enumerates or removes old ones. The 79 MB `state.sqlite` sits there,
  bit-for-bit intact, forever, under its old hash.
- `get_vault_cache_dir`'s hash is a **pure, deterministic function of the
  resolved path string** (`hashlib.sha256(str(resolved).encode()).hexdigest()[:16]`,
  `config.py:357-358`). This means recovery is not a mystery-guess — it is a
  one-line reproducible computation: `python3 -c "import hashlib;
  print(hashlib.sha256(str(Path('second_brain-2026').resolve()).encode()).hexdigest()[:16])"`
  gives the *new* key the phantom DB was created under; the *old* key is
  whatever the same formula gives for the pre-rename path, which is generally
  recoverable from `.cache/vaults/*/vault_root` (every cache dir carries a
  plaintext marker file naming the exact path it was created for — I verified
  this marker write at `config.py:185-186`, and the storage proposal's own §0
  used exactly this marker to identify `13ed51f8b06cb88e` in the first place).
  A `grep -l <old-vault-name> .cache/vaults/*/vault_root` finds it in seconds.
  Once found, `mv .cache/vaults/<old-hash> .cache/vaults/<new-hash>` is a
  complete, lossless fix — no export/import needed, because nothing was ever
  destroyed.
- Even without noticing the orphan at all, STORAGE F2's own investigation
  (§ below) establishes that `.curator/sync/dev-*.jsonl` **inside the renamed
  vault** independently carries a near-complete snapshot of the same data,
  refreshed automatically by every mutating command. So there is a second,
  independent recovery path even if the first is never discovered.

So the accurate description of F1 is: *a silent, undetected, no-warning
divergence that causes `wiki status` to report a false "0 sources" on a
healthy vault* — a real, P1-grade correctness/trust bug (the tool lies about
vault health with no error, exactly the class of bug this project's own
`ledger.md`/HITL-truthfulness culture treats seriously) — but it is not data
loss. Nothing is destroyed, corrupted, or served wrong to a query (a renamed,
un-recovered vault just looks *empty*, it doesn't serve *fabricated*
knowledge). That is a P1 by the brief's own rubric, not P0.

**Verdict: DOWNGRADED P0 → P1.** Mechanism confirmed, reachability confirmed,
"orphans" is the right word — "destroys" is not. Recommended fix direction is
also worth correcting: the storage proposal implies restructuring where
`state.sqlite` lives (moving it vault-side, or persisting an old→new key
migration). The **cheaper, more targeted fix** is (a) make `db.connect()`'s
self-heal loud when it fires against a path whose parent vault directory is
non-trivial (e.g., `Collections/` already has hundreds of files — a fast,
one-line heuristic check before silently creating a fresh schema), and/or (b)
persist a reverse index (`vault_root` marker files already exist for every
cache dir — a `wiki status` health check could scan `.cache/vaults/*/vault_root`
for a plausible near-match and warn: *"No cache found for this vault, but a
cache exists for a similarly-named/nearby path — did you rename or move the
vault?"*). Neither requires moving `state.sqlite`'s physical location.

---

## STORAGE F2 — [P0 claimed] `.cache` loss is instant, total, unrecoverable loss

### Attack 1: self-heal / zeroed-stats claim

Confirmed independently: `get_stats` (`db/schema.py:962+`) does
`if not db_path.exists(): return {"sources_total": 0, ...}` — a zeroed dict,
not an exception. Combined with Attack 1 above (unconditional self-heal on
`connect()`), a `.cache` wipe followed by any `wiki` command does produce a
silently-recreated empty schema with no error surfaced. **Attack fails on
this narrow point — mechanism is real.**

### Attack 2 (the one that lands): is it actually true there is "no path back
except a full source-by-source re-ingest"?

This is the load-bearing claim of F2, and it is **false as stated**. I traced
the recovery path the proposal did not check: the project already ships a
working device-to-device sync/export mechanism whose export artifact happens
to live **inside the vault** and happens to be **default-on**.

**The mechanism, read from source, not inferred:**

`config.py:291-300` (the `auto_sync` config block, comments intact):
```python
"auto_sync": {
    # Cross-device knowledge auto-sync over Syncthing (one-writer-per-file).
    # Default-on since v0.30.0 (opt-out): mutating CLI commands
    # (add/build/sync/update) write this device's .curator/sync/dev-<id>.jsonl
    # at the end, LWW-gated so unchanged state is not re-exported. ...
    # Without Syncthing the export is a harmless local file.
    "enabled": True,
    "dir": "sync",
    ...
},
```

`_maybe_auto_export_impl` (`commands/common.py:1747-1770`) runs after every
mutating command (add/build/sync/update) when this default-on flag is set,
and calls `db_sync.export_for_device`, which writes a **full table snapshot**
(not a delta — confirmed by its own docstring at `db_sync.py:1471`: *"A full
snapshot (not a delta) is written so a late-joining peer always receives the
complete view this device holds"*) to `.curator/sync/dev-<device_id>.jsonl`.

`SYNC_TABLES` (`db_sync.py:37-61`) — the list of tables this export covers —
is:
```
deleted_records, sources, source_pages, source_pdf_pages, atoms, concepts,
synthesis_nodes, source_spans, knowledge_units, claim_supports,
compiler_generations, graph_entities, graph_relations,
graph_relation_supports, entity_aliases, entity_merge_proposals,
entity_resolution_lineage, community_reports, dag_edges,
artifact_dependencies, curation_plans, insight_candidates, prompt_runs,
query_traces, memory_paths, synthesis
```

This is **exactly** the set F2 calls irreplaceable. Compare directly against
F2's own text: *"Every `dag_edges` row... every HITL ledger-linked DB state...
is gone, with no path back."* `dag_edges` is in `SYNC_TABLES`. So is every
graph/entity/relation/community-report table, `source_spans`,
`knowledge_units`, `insight_candidates`, and `curation_plans` (the actual
HITL-linked tables). None of this is gone if a `.curator/sync/dev-*.jsonl`
file exists — and per `00_problem.md`'s own measured baseline, **it does**:
`.curator/sync/` in the live vault is 24 MB across two files, one written
**today** (2026-08-06).

**Recovery is one command:** `wiki db import
.curator/sync/dev-<device-id>.jsonl` against the freshly self-healed empty DB
performs an LWW merge where every local row is absent, so every row in the
file is inserted. `_resolve_root_or_die()` does not require `state.sqlite` to
exist or be non-empty — it only reads `.curator/settings.yml` — so this
command is reachable immediately after the exact disaster F2 describes, no
special recovery mode needed.

**It gets stranger — and worse for F2's "no path back" framing — under the
exact scenario F2 names (`.cache` wipe via re-clone/disk cleanup):**
`get_device_id` (`db_sync.py:669-677`) reads/writes `device_id` via
`read_sync_state`, whose path (`db_sync.py:589-594`) is
`cfg.get_global_config_dir() / "sync_state" / "<vault_key>.json"` — the
**same** repo-anchored global cache dir F2 says gets wiped. So a `.cache`
wipe erases the device's own `device_id` alongside `state.sqlite`. The next
`get_device_id()` call mints a **new** random id. Consequence: the *old*
`dev-<old-id>.jsonl` file sitting in `.curator/sync/` (vault-side, survives
the wipe untouched) no longer matches the "own file" exclusion in
`_peer_files` (`db_sync.py:1501-1514`, `own = f"dev-{own_device_id}.jsonl"`).
It is now indistinguishable from a genuine peer device's export. Running the
already-documented `wiki db autosync` — not even a disaster-recovery-specific
command, just the normal cross-device sync command — would import it
automatically via `import_all_peers`, with no special knowledge required
about what happened.

**What is genuinely NOT recovered by this path** (and this is the honest,
surviving core of F2, just narrower): `EXCLUDE_TABLES`
(`db_sync.py:67-76`) — `ingest_jobs`, `job_events`, `ingest_runs`,
`search_embeddings`, `search_index_meta`, `search_documents*`, `page_hashes`,
`schema_version`. Of these: `ingest_runs`/`ingest_jobs`/`job_events` are
operational audit-trail loss (real, but not "knowledge base" loss — nothing
the project calls "sole source of truth" — `source_spans`/`knowledge_units`
etc. — lives here). `search_embeddings`/`search_index_meta`/`search_documents*`
are explicitly derived/regenerable via `wiki reindex --embed` (costly, not
irreplaceable — same status as re-emitted `Collections/` markdown).
`page_hashes` feeds `wiki sync`'s change-detection; losing it forces one full
re-verification pass, not data loss.

**Verdict: DOWNGRADED P0 → P1.** The mechanism (self-heal, silent, no
warning) is real and the finding correctly identifies a genuine gap (job
queue/audit history has no recovery path, and the DAG-table recovery path
that *does* exist is completely undocumented as disaster recovery and not
triggered automatically on self-heal). But "instant, total, unrecoverable
loss of the sole source of truth" is not what happens — most of what the
project itself defines as "the sole source of truth" in `AGENTS.md`
(*"Holds source_spans, knowledge_units, graph entities/relations,
community_reports, synthesis_nodes, dag_edges, job queue"*) survives via a
mechanism that is default-on and was already firing in this exact vault the
day of this audit. The corrected fix direction: don't redesign the storage
topology — (1) make the empty-schema self-heal detect and warn when it fires
against a vault whose `.curator/sync/*.jsonl` files are non-trivial (a "this
looks like a reset, not a fresh vault — recover via `wiki db import
<file>`?" prompt), and (2) close the real remaining gap by deciding whether
`ingest_runs`/`ingest_jobs` audit history is worth adding to `SYNC_TABLES` or
is acceptably ephemeral (it currently isn't a documented decision either
way — that omission is a legitimate, narrower finding worth keeping).

---

## DERIVED F1 — Chat sidebar reads a dead `runtime/jobs.json`

### Attack 1: re-derive from source independently, don't trust the pasted excerpt

Read `plugin/src/ui/chat/ChatSidebarView.ts:465-491` directly:

```ts
private updateStatusBar(): void {
  if (!this.statusBarEl) return;
  try {
    const vaultRoot = (this.plugin.app.vault.adapter as any).getBasePath?.() || "";
    if (!vaultRoot) return;
    const jobsPath = join(vaultRoot, ".curator", "runtime", "jobs.json");
    const statusPath = join(vaultRoot, ".curator", "runtime", "status.json");

    this.statusBarEl.empty();

    if (existsSync(jobsPath)) {
      const raw = readFileSync(jobsPath, "utf8");
      const data = JSON.parse(raw);
      if (data.running && data.running.length > 0) { ... }
      else if (data.queued && data.queued.length > 0) { ... }
    }
  } catch (e) {
    // fail silently
  }
}
```

Matches the proposal's excerpt exactly, line-for-line. `statusPath` (line 471)
is indeed computed and never referenced again in the function — dead local,
confirmed by reading the full 27-line body. No fallback of any kind: no
`catch` handler does anything but swallow, no call to `IncuratorClient`, no
call to a backend command. **Attack on "no fallback exists" fails — the claim
is exactly correct.**

### Attack 2: independently confirm the path mismatch and staleness, don't trust the pasted `cat` output

```
$ ls -la /Users/shin/shinywings/second_brain/.curator/runtime/
jobs.json     4841 bytes   Jul  4 13:08
sources.json 20641 bytes   Jul  4 13:08
status.json   4717 bytes   Jul  4 13:08

$ ls -la /Users/shin/shinywings/Incurator/.cache/vaults/13ed51f8b06cb88e/runtime/
jobs.json     1435 bytes   Aug  5 21:12
sources.json 26181 bytes   Aug  5 21:12
status.json   4775 bytes   Aug  5 21:12
```

Content independently re-read: the vault-side file has `"generated_at":
"2026-07-04T04:08:41Z"`, `"running": []`, `"queued": []`, permanently — the
repo-cache file has `"generated_at": "2026-08-05T12:12:40Z"` with an actively
`"running"` job (`job_id: 40`, `phase: "l3_concepts"`, `progress: 0.75`).
These are unambiguously different files with different content, confirming
`existsSync(jobsPath)` is always true (file exists, just dead) and the code
reads a plausible-but-wrong answer forever. **Attack fails — independently
reproduced, not just re-quoted from the proposal.**

### Attack 3: is there really no fallback anywhere, even outside this one function?

I checked whether `IncuratorClient` (used extensively elsewhere in this same
file for `getSourceStatus`, `rebindSource`, `ingestPdf`, etc.) exposes any
general status/jobs method the sidebar could already be calling but isn't —
found none (`grep -n "class IncuratorClient\|async .*[Ss]tatus"
plugin/src/agent/incuratorClient.ts` surfaces only source-specific and
git-specific status methods, nothing job-queue-shaped). I also checked
whether this bug was ever noticed and left broken across multiple later
edits to the same file, rather than being a fresh regression no one has had
a chance to see: `git log` on `ChatSidebarView.ts` shows edits on
2026-07-19, 2026-07-26 (×2), 2026-08-01 (×2), and 2026-08-06 — all **after**
the July 6 relocation — none touch `updateStatusBar`. This is not a fresh
regression sitting undiscovered for days; it is dead code that survived six
subsequent edit passes to the same file. **Strengthens, does not weaken, the
finding.**

### Attack 4 (the one real correction): is "no workaround" accurate, and is the implied fix direction right?

Two nuances the proposal underweights:

1. **A workaround does exist**, just not in the same UI surface: the
   `IncuratorDashboardModal` already solves this exact problem correctly.
   Reading it (`plugin/src/ui/incuratorDashboardModal.ts:203-233`):
   ```ts
   private async fetchLiveStatus(force = false): Promise<{...} | null> {
     ...
     this._liveStatusPromise = this.runWikiCommand(["status", "--json"]).then(...)
     ...
   }
   ```
   confirmed live-shells `wiki status --json` and never touches the on-disk
   snapshot directly — and `readRuntimeJson`/`readFreshRuntimeJson`
   (`:235-245`), despite their filesystem-suggesting names, are themselves
   just thin wrappers around `fetchLiveStatus()`, not raw reads. So a user
   who wants an accurate "is something running" signal can open the
   dashboard instead of relying on the chat sidebar's spinner. The brief's
   P1 rubric (*"user-visible breakage with no workaround"*) is not cleanly
   met — I'd flag this as a documented tension rather than a full
   downgrade, because the workaround requires the user to already know the
   sidebar indicator is untrustworthy and switch UI surfaces, which is not
   a real workaround for someone who doesn't yet know the bug exists. Net:
   **P1 stands**, but note the rubric tension explicitly in the writeup
   rather than asserting "no workaround" flatly.

2. **The natural-sounding fix ("point `jobsPath` at the correct repo-cache
   absolute path") is not actually available.** I grepped the entire plugin
   source for any logic that mirrors the backend's
   `hashlib.sha256(str(resolved_vault_path)).hexdigest()[:16]` vault-key
   derivation (`grep -rn ".cache/vaults\|vault_key\|vaultKey\|sha256"
   plugin/src` — zero matches anywhere in `plugin/src`). The plugin has no
   way to compute `<repo-root>/.cache/vaults/<hash>/runtime/jobs.json` from
   TypeScript — it doesn't know where the backend repo lives on disk, and
   duplicating the hash function would still leave it guessing the repo
   root. The **only** viable fix is the one the dashboard modal already
   uses: shell out to `wiki status --json` (or a lighter equivalent) rather
   than read any file directly. This should be stated explicitly as the fix
   direction in the master plan, not left implied by the dashboard
   contrast — a naive "fix the path" patch would not compile into working
   code without also inventing new plumbing the dashboard already has.

**Verdict: CONFIRMED, P1 stands.** This is the strongest finding in either
proposal — every claim independently re-derived from source and from live
files, not just re-quoted. The only corrections are (a) note the rubric
tension around "no workaround" rather than asserting it flatly, and (b)
specify the fix as "adopt `runWikiCommand(["status","--json"])` /
`fetchLiveStatus()`-style live query," not "fix the path," since no path fix
is possible from the plugin side alone.

---

## Secondary spot-checks (not the assigned focus, brief notes only)

These were not the primary target of this pass but came up naturally while
reading the same files; flagged briefly rather than deep-dived.

- **STORAGE F5** (`.stignore` staleness): the proposal's quoted excerpt of
  the live vault's `.stignore` is **incomplete**. I read the file directly
  and it contains a *third* stale block the proposal's quote omits:
  ```
  // Incurator runtime: 백엔드 실시간 작업 상태 파일 (휘발성)
  // 짧은 주기로 업데이트되므로 동기화 시 심각한 충돌과 트래픽 유발
  .curator/runtime/
  ```
  This does not weaken F5 — if anything it strengthens it (three dead rules
  tied to pre-July architecture, not two) — but the evidence as filed is
  incomplete and should be corrected before this reaches synthesis. It also
  usefully corroborates DERIVED F2: the live vault's `.curator/runtime/`
  fossils were deliberately Syncthing-excluded from the start (marked
  "volatile"), which is a plausible partial explanation for why no one
  noticed they'd gone stale — they were never expected to converge across
  devices, only within one, and even that broke silently in the July 6
  relocation.
- **DERIVED F3/F4** (sync-report.json worker-path staleness; `wiki sync`'s
  false success message): both independently spot-checked and confirmed —
  `grep` of `ingest_worker.py` for `sync_report`/`_write_latest_sync_report`
  returns zero matches (confirms F3's "never called from the worker" claim),
  and `sync.py:1077-1087`'s `finalize_routing_tables` body indeed calls only
  `rebuild_index` + `append_log_entry`, while `commands/core.py:1313` prints
  `"Routing tables rebuilt (index.md, ledger.md, log.md, overview.md)"`
  regardless — the message names two files the function body never touches.
  Both stand as filed.

## What survives to synthesis

- STORAGE F1: real, P1 (not P0) — silent orphan, not data loss; fix should
  target loud self-heal + reverse-lookup warning, not storage relocation.
- STORAGE F2: real, P1 (not P0) — silent self-heal, but the framing of
  "unrecoverable" is false; the actual gap is (a) the existing
  sync-jsonl recovery path is undocumented/non-automatic, and (b) job
  queue/ingest-run audit history has no recovery path at all. The master
  plan should propose making self-heal loud/detectable and wiring or
  documenting `wiki db import` as the recovery step, not restructuring
  where `state.sqlite` lives.
- DERIVED F1: real, P1, confirmed independently down to byte-for-byte file
  diffs — the strongest finding examined in this pass. Fix direction must be
  "call the backend live status command," not "fix the file path," because
  the plugin cannot compute the correct path.

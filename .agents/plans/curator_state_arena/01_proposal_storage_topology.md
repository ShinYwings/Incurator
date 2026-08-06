# Inspector Report: `storage_topology` (Observation A)

Date: 2026-08-06 | master @ `02faa0a` (v0.46.0) | Method: read-only measurement
per `00_problem.md`. No code, docs, config, vault, or DB was modified. The live
DB was only ever opened `?mode=ro` via the `sqlite3` CLI for `SELECT`s.

## 0. How the hash and the 0-byte file were confirmed

```
$ python3 -c "import hashlib; from pathlib import Path; \
  p = Path('/Users/shin/shinywings/second_brain').resolve(); \
  print(hashlib.sha256(str(p).encode()).hexdigest()[:16])"
13ed51f8b06cb88e            # matches .cache/vaults/13ed51f8b06cb88e exactly

$ cat .cache/vaults/13ed51f8b06cb88e/vault_root
/Users/shin/shinywings/second_brain

$ stat -f "size=%z" .cache/vaults/13ed51f8b06cb88e/state.sqlite
size=79134720
$ sqlite3 "file:.../13ed51f8b06cb88e/state.sqlite?mode=ro" \
  "SELECT count(*) FROM sources; SELECT count(*) FROM sqlite_master WHERE type='table';"
36
50

$ stat -f "size=%z mtime=%Sm" /Users/shin/shinywings/second_brain/.curator/state.sqlite
size=0 mtime=Jul 30 17:31:00 2026
$ sqlite3 "file:/Users/shin/shinywings/second_brain/.curator/state.sqlite?mode=ro" \
  "SELECT count(*) FROM sqlite_master;"
0                             # no error — SQLite accepts a 0-byte file as a
                              # trivially valid, empty database, even in ro mode
```

`.cache/vaults/` on this machine currently holds **27** distinct vault-key
directories (`ls -la` enumerated, `vault_root` marker read for each). All but
one resolve to ephemeral `/private/var/…/T/tmp*` pytest/CI dirs or
`.../scratchpad/...` agent worktrees — expected churn. The one durable,
non-ephemeral entry is `13ed51f8b06cb88e` → `/Users/shin/shinywings/second_brain`,
and `023260bfdff2e73a` → `/Users/shin/shinywings/Incurator/testbed` (see F5).

## 1. Where the code actually puts `state_db`

`WikiPaths.state_db` (`backend/src/curator/config.py:180-189`):
```python
@property
def state_db(self) -> Path:
    """Machine-local SQLite metadata and provenance replica."""
    cache_dir = self.machine_cache
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "vault_root").write_text(...)
    return cache_dir / consts.STATE_DB
```
`machine_cache` (`config.py:97-100`) → `get_vault_cache_dir(self.root)`
(`config.py:357-361`):
```python
def get_vault_cache_dir(root: Path) -> Path:
    resolved = Path(root).expanduser().resolve(strict=False)
    vault_key = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:16]
    return get_global_config_dir().parent / "vaults" / vault_key
```
`get_global_config_dir()` (`config.py:351-354`) is `Path(__file__).resolve().parents[3]
/ ".cache/config"` — **anchored to wherever the installed `curator` package's
`config.py` physically lives** (for this dev checkout, that resolves to
`<repo root>/.cache/config`, sibling `.cache/vaults/`). It is not anchored to
the vault at all. `.venv` and `.venv-dev` are editable installs (verified via
their `.pth` files pointing at `backend/src`), so both load this exact source
file — no drift between installed copies on this machine.

`db.connect()`/`db.init_db()` (`backend/src/curator/db/schema.py:906-944`) are
the only writers of the schema, and grep confirms `consts.STATE_DB` is
constructed at exactly **one** production call site
(`config.py:189`, inside `WikiPaths.state_db`) — no code anywhere resolves
`paths.internal / "state.sqlite"` (the vault-local path) directly.

## 2. What created the 0-byte `.curator/state.sqlite` — migration history

`git log` on `config.py` surfaces the exact lifecycle:

- **`6556fc5`** (2026-07-06, *"feat(paths): relocate device-local state to
  repo cache"*, this is the v0.32.1 release) introduced `machine_cache`/
  `get_vault_cache_dir` and a `prepare_machine_state()` that performed a
  **one-time migration**: if `paths.internal/state.sqlite` (old) and the new
  cache path both existed, it raised
  `RuntimeError("Both vault-local and repo-cache state databases exist; refusing to choose between …")`;
  otherwise it `shutil.move`d the old file (+ `-wal`/`-shm` sidecars) into the
  cache dir, keeping a timestamped backup under
  `.cache/migrations/v0.32.1/<stamp>/`.
- **`f8b40be`** (2026-07-07 09:30, *"feat(core): remove v12 migration backward
  compatibility and schema fallback"*, **one day later**) deleted that entire
  block. The current `prepare_machine_state()` (`config.py:364-369`) only
  `mkdir`s the cache dir and writes the `vault_root` marker — it no longer
  checks for, reacts to, or warns about a leftover `.curator/state.sqlite`.
- `CHANGELOG.md:934-938` (`[0.32.1]` entry) still asserts the guarantee that
  commit `f8b40be` deleted: *"A one-time migration moves the existing
  `.curator/state.sqlite` (and sidecars) to the new location; if both old and
  new DB files exist, the backend aborts with explicit recovery
  instructions."* This is no longer true of the code.

The observed file (0 bytes, mtime **2026-07-30**, three weeks after the guard
was removed) cannot be attributed to any current code path — the single
`STATE_DB` call site targets `machine_cache`, not `.curator/`. Its precise
origin (manual `touch`, an editor/backup tool probing the path, an interrupted
process) is not determinable from static/measured evidence and is not
asserted here. What *is* measured and load-bearing is the mechanism that would
make such a file dangerous rather than inert — see F2.

## 3. What the docs claim (quoted)

**CLAUDE.md:415-433** ("Vault Structure" ASCII tree) places `state.sqlite`
physically inside `.curator/`:
```
└── .curator/          [Machine Space] Hidden core (managed by wiki CLI)
    ├── settings.yml   Vault-scoped portable settings (persona, sync policy, etc.)
    ├── state.sqlite   Dedup hashes, run history, provenance
    ├── index.md       DAG routing table (all L1-L4 node IDs)
    ├── overview.md    Domain manifest
    ├── log.md         Append-only event log
    ...
```
`log.md` is listed the same way — also wrong post-migration (`log.md` now
resolves to `machine_cache / consts.LOG_FILE`, `config.py:114-116`).

**AGENTS.md:221, 404** (the file CLAUDE.md is contractually required to stay
synchronized with) has no "Vault Structure" tree at all, so it does not repeat
the specific error, but doesn't correct it either:
> `state.sqlite` = single source of truth. Holds source_spans, knowledge_units,
> graph entities/relations, community_reports, synthesis_nodes, dag_edges, job
> queue.
> `.curator/` is machine-readable Curator state. Modify it only through the
> project code or explicit testbed setup scripts.

**`docs/specs/curator_schema/SCHEMA.md:17-58`** is correct and current
(v0.46.0) — it draws the `.curator/` tree with **no** `state.sqlite` in it,
then separately shows machine-local state at the repo root:
```
.curator/                          # <- no state.sqlite here
├── settings.yml
├── sync/…
├── sessions.json
├── zotero_profiles.json
└── Collections/…

.cache/
├── config/
└── vaults/<vault-key>/
    ├── state.sqlite          # authoritative local replica
    ...
```
and explicitly: *"Machine-local files must never fall back into the
synchronized vault. Storage isolation is structural and does not depend on
`.stignore`."* (line 54-55).

**`docs/specs/system_behavior/SYSTEM_BEHAVIOR.md` contradicts itself.**
§2.1 (line 34) and §13.1 (line 1250) correctly say *"repo-cache `state.sqlite`"*.
But §22.3 "Directory Roles" (lines 1953-1955) says:
> `.curator/` — AI-Only Space: `state.sqlite` (source of truth), DB-native
> search indexes/traces, the derived `Collections/` Obsidian projection, and
> `runtime/` snapshots. Hidden; not a user concern.

This is the same document, same version line, asserting two different
physical locations for the same file 1900 lines apart.

## 4. Findings

### F1 — [P0] Vault rename/move silently orphans the real DB and self-heals a fresh empty one at the new key, with no error at any layer
**Measurement:** `get_vault_cache_dir` (`config.py:357-361`) hashes
`str(Path(root).expanduser().resolve(strict=False))`. There is no persisted
old-key→new-key mapping and no reverse scan of `.cache/vaults/*/vault_root`
for a match on rename — verified by reading the full body of
`get_vault_cache_dir` and `prepare_machine_state` (`config.py:364-369`):
neither does anything but hash-and-mkdir. `db.connect()`
(`db/schema.py:926-944`) unconditionally runs
`conn.executescript(SCHEMA_SQL)` on every open — the code comment at
`schema.py:936` literally says *"Self-heal for existing empty/corrupted state
DB files missing base tables."*
**Failure scenario:** rename `second_brain/` → `second_brain-2026/` (or move
it to a new parent directory — an ordinary, non-exotic user action). The next
`wiki status` computes a brand-new sha256 prefix, finds no cache dir, creates
one, and `db.connect()` silently builds a full empty schema in it. The command
succeeds, reports a plausible-looking near-empty vault (0 sources), and gives
no indication that the real 79 MB / 36-source / 1371-node DB is still sitting,
untouched and unreferenced, under the old hash. Nothing short of manually
diffing `.cache/vaults/*/vault_root` would reveal the orphan.

### F2 — [P0] `.cache` loss (repo re-clone, disk cleanup, ephemeral CI/container disk) is instant, total, unrecoverable loss of the sole source of truth, while the vault directory looks completely intact
**Measurement:** `get_global_config_dir()` (`config.py:351-354`) is
`Path(__file__).resolve().parents[3] / ".cache/config"` — for this editable
install that resolves inside the git working tree itself
(`<repo>/.cache/config`), sibling to `.cache/vaults/`. `db.get_stats`
(`db/schema.py:962-969`, confirmed by reading the guard) returns a **zeroed
stats dict**, not an exception, `if not db_path.exists()`. Per the shared
architecture memory (`AGENTS.md:221-222`, `CLAUDE.md:291`), `state.sqlite`
alone holds `source_spans`, `knowledge_units`, `dag_edges`, the job queue, and
`community_reports` — none of which exist in `.curator/Collections/`
(explicitly "derived disposable search corpus... not authoritative").
**Failure scenario:** `git clone` the repo fresh onto a new machine (or after
a local disk wipe), point it at the existing, Syncthing-preserved vault
directory, run `wiki status`. `.cache/` doesn't exist yet, so a brand-new
empty vault-key directory is created and `db.connect()` self-heals a valid
empty schema into it — again, no exception. The vault folder (`Collections/`,
`index.md`, `overview.md`, `sessions.json`, `sync/*.jsonl`) is present and
looks healthy; the CLI reports "0 sources" rather than "database missing."
Every `dag_edges` row, every job-queue/ingest-run history row, every HITL
ledger-linked DB state, and every chunk embedding for the 36 registered
sources is gone, with no path back except a full source-by-source
`wiki add`/`wiki build` re-ingest (lossy: loses ledger corrections and insight
promotion history that lived only in DB tables, not in the markdown
projections).

### F3 — [P1] The one-time migration + hard dual-existence abort was deliberately deleted one day after being added; the CHANGELOG still documents a safety net that no longer exists in code
**Measurement:** see §2 above — commits `6556fc5` (2026-07-06) → `f8b40be`
(2026-07-07 09:30) are one calendar day apart. `git show f8b40be -- backend/src/curator/config.py`
shows the entire `RuntimeError` dual-existence guard and the
`shutil.copy2`/`shutil.move` migration body deleted, replaced by a 5-line
`prepare_machine_state` that only creates the cache dir and writes the
`vault_root` marker. `CHANGELOG.md:934-938` (`[0.32.1]`) is unrevised and
still promises the abort behavior.
**Failure scenario:** this is not hypothetical — it is the exact state
`00_problem.md` opens with. The live vault has **both** a `.curator/state.sqlite`
(0 bytes) and a repo-cache `state.sqlite` (79 MB) simultaneously. Under the
v0.32.1 design this dual-existence would have been a loud, blocking
`RuntimeError` the first time any `wiki` command ran, forcing investigation
before any further writes. Today it produces total silence — the DB is used
normally, and the anomaly was only found by manual filesystem inspection for
this audit, not by any guard the system runs on its own.

### F4 — [P2] `CLAUDE.md` and `SYSTEM_BEHAVIOR.md §22.3` both mis-locate `state.sqlite` inside `.curator/`, contradicting the current, correct `SCHEMA.md` and contradicting other sections of `SYSTEM_BEHAVIOR.md` itself
**Measurement:** quotes captured in full in §3 above, with line numbers:
`CLAUDE.md:415-433`, `SYSTEM_BEHAVIOR.md:1953-1955` vs.
`SYSTEM_BEHAVIOR.md:34,1250`, `SCHEMA.md:17-58`. `AGENTS.md` has no
"Vault Structure" tree to check against CLAUDE.md's per the project's own
"Agent Rule Synchronization" mandate (CLAUDE.md's own header: *"CLAUDE.md...
must stay synchronized with... AGENTS.md"*) — so the stale tree in CLAUDE.md
isn't even mirrored, it's unilaterally wrong relative to the sibling doc it's
supposed to track.
**Failure scenario:** an agent or new contributor reading CLAUDE.md's
authoritative-looking tree diagram (which is what every session in this repo
loads verbatim per the system prompt) reasonably concludes `.curator/state.sqlite`
is the real DB path and could, e.g., `sqlite3 .curator/state.sqlite` for manual
inspection/backup, silently getting the empty decoy instead of the real 79 MB
file — or conversely conclude the vault backup already covers the DB, which
F1/F2 show it structurally cannot. `SYSTEM_BEHAVIOR.md`'s internal
self-contradiction (§2.1 vs §22.3 in the one file this repo calls "the
absolute behavior source of truth") means even resolving the conflict by
"trust the deepest spec" doesn't fully work without also reading the older
CHANGELOG/commit history done in this report.

### F5 — [P2] `.stignore` is generated once and never migrated forward; the live vault's copy still targets the pre-July architecture and gives zero coverage to anything that matters today
**Measurement:** `commands/core.py:272-277`:
```python
stignore_src = templates_dir / "stignore.template"
stignore_dest = root / ".stignore"
if stignore_src.exists() and not stignore_dest.exists():
    shutil.copy2(stignore_src, stignore_dest)
```
— only written if absent, never diffed/updated on subsequent `wiki init` runs.
The live vault's `.stignore` (`/Users/shin/shinywings/second_brain/.stignore`,
mtime **2026-06-04**, a month before the 2026-07-06 migration) still contains,
verbatim:
```
// Incurator backend: 기기별 인덱스 상태
// 다른 기기 위에 덮어쓰면 재인덱싱 필요; vault 파일은 Syncthing이 동기화
.curator/state.sqlite
.curator/qmd/index.sqlite
```
(`qmd` is the pre-v0.3.2 search index, already retired per project memory.)
The **current** shipped template
(`backend/src/curator/workspace/templates/stignore.template`, read in full)
has already dropped all three of `.curator/state.sqlite`, `.curator/qmd/`, and
`.curator/runtime/` — because none of those paths are written inside `.curator/`
by current code, so no ignore rule is needed for a *new* vault. But this vault
was initialized before the template changed, and nothing reconciles it
afterward. `.stfolder`/`.stversions` presence in the vault confirms Syncthing
is genuinely active here, not theoretical (`.stversions/.curator/sync/` exists
with archived conflict copies; no `state.sqlite` entries were found there,
consistent with the ignore rule successfully keeping Syncthing away from it
today).
**Failure scenario:** none of this vault's `.stignore` entries are wrong
enough to cause active sync corruption right now (the paths they name are
simply dead), but the pattern generalizes badly: `SCHEMA.md:54-55` explicitly
says storage isolation "does not depend on `.stignore`" for *current* code —
yet the actual protection for the pre-migration file that exists on disk
*right now* is coming entirely from this one stale, hand-authored,
never-revalidated line. If a future path relocation isn't paired with a
mechanism to update already-initialized vaults' `.stignore` files, the same
gap reopens for whatever moves next.

### F6 — [P3] The observed 0-byte `.curator/state.sqlite` is not currently load-bearing, but the mechanism that makes it a live trap (silent empty-file self-heal) is real, measured, and un-flagged
**Measurement:** confirmed empirically in §0 — `sqlite3 "file:<0-byte path>?mode=ro" "SELECT count(*) FROM sqlite_master"` returns `0` with **no error**, not `Error: file is not a database`. Combined with `db/schema.py:936`'s explicit self-heal comment and unconditional `executescript(SCHEMA_SQL)`, any code path — now or introduced later — that resolves `paths.internal / "state.sqlite"` instead of `paths.state_db` would succeed silently and begin operating against a phantom, schema-valid, permanently-diverged knowledge base, indistinguishable from the real one without a byte-for-byte / row-count check. Grep confirms zero such call sites exist in `backend/src` today (only test fixtures under `backend/tests/` construct that path, and only to set up isolated test vaults, not to exercise this trap) — this finding is about the mechanism's blast radius, not a currently-active bug.
**Failure scenario:** a future contributor "fixing" `WikiPaths` (e.g. reverting F1/F2's repo-cache design, or adding a code path that reads config before `state_db` normalizes it) reintroduces a direct `paths.internal / STATE_DB` reference. Nothing in `db.connect()`/`init_db()` would catch it — the self-heal is specifically designed to accept and repair empty files, which is correct behavior for a *legitimately new* vault but indistinguishable from *silently connecting to the wrong file* for an established one.

## 5. Consequences — direct answers to the brief's four questions

- **Vault backup / Obsidian sync never carries the DB.** Structural, not
  incidental: `state_db` is computed from `get_global_config_dir()`, which is
  anchored to the installed package location, never to `self.root` (the
  vault). Backing up or Syncthing-syncing `second_brain/` captures
  `Collections/`, `sync/*.jsonl`, `sessions.json`, and the 0-byte decoy — none
  of which reconstruct `dag_edges`, the job queue, or embeddings (F2).
- **The cache is keyed to the repo, not the vault.** `get_global_config_dir()`
  parents-walks from the *installed package's* `__file__`, so a second git
  checkout of this same repo (or a re-clone after loss) computes a *different*
  `.cache/` root even for the *identical* vault path — it isn't just
  "repo-local," it's local to *this specific working tree* (F2).
- **Repo re-cloned / cache cleared:** total, silent, self-healing loss (F2) —
  confirmed the failure mode is "reports empty vault," not "errors out,"
  because `get_stats` returns zeroed counts rather than raising when
  `db_path` doesn't exist.
- **Vault moved or renamed:** silent orphan + silent phantom replacement (F1)
  — the sharpest reproducible version of this on this very machine is not a
  hypothetical rename but **`VAULT_ROOT=testbed` resolved from different
  working directories**: `_resolve_root_or_die_impl`
  (`backend/src/curator/commands/common.py:248-269`) does
  `root_path = Path(env_root).resolve()` — relative to **cwd at invocation**,
  not to any fixed repo root. `VAULT_ROOT=testbed wiki status` is CLAUDE.md's
  own documented dev command. Two agents (or two Bash tool calls with
  different working directories — explicitly possible per this environment's
  own "cwd resets between calls" note for subagents) invoking that exact
  documented command from different cwds compute different sha256 keys for
  what both believe is "the testbed," landing on disjoint, mutually invisible
  caches. Measured: `.cache/vaults/023260bfdff2e73a/vault_root` =
  `/Users/shin/shinywings/Incurator/testbed`, confirming this is exactly how
  that one entry was produced from the repo-root cwd; any other cwd running
  the same env-var command would mint a sibling entry instead of reusing it.
- **Two vaults colliding on a hash:** sha256 truncated to 16 hex chars is 64
  bits of entropy — a true collision between two *different* real vault path
  strings is not a practical risk at the vault counts this project will ever
  reach. The realistic risk runs the other direction and is already covered
  above: the *same* logical vault producing *different* keys depending on how
  its path string is spelled at invocation time (relative vs. absolute,
  differing cwd, symlink vs. real path) — divergence, not collision.

## 6. Cross-check against `backend/tests/`

`backend/tests/test_db_autosync.py` and `test_s2_cli_correctness.py` /
`test_mcp_degraded_warnings.py` construct `.curator/state.sqlite` paths
directly — but always inside a fresh `tmp_path` fixture to build an isolated
DB for the test, never through `paths_from_config`/`WikiPaths`, and never as
an assertion that production code should resolve `state_db` to that location.
No test pins the "both old and new DB files → hard abort" contract described
in CHANGELOG.md:934-938; grepping `test_config` and `test_paths`-named test
files for `RuntimeError` + `"Both vault-local and repo-cache"` found no match,
consistent with F3 (the guard was removed in code, and no regression test was
left behind to catch its absence).

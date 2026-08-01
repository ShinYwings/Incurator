# v0.40.0 Persistence Review Evidence Ledger

Date: 2026-08-01
Rollback anchor: `268d6c3f019c7a04510e21c2d05522fc89d31315`

## Pre-implementation reality

- Branch: `release/v0.39.3`; draft PR #104 targets `master`.
- `save_config()` passes `lambda _existing: deepcopy(vault_only)`, so the
  mapping loaded under the lock is discarded. Isolated reproduction loses a
  peer-only key added after the stale snapshot.
- `writeMergedSessionStore()` and `saveZoteroProfiles()` read canonical JSON,
  merge in memory, then rename a temp unconditionally. An injected peer
  replacement between read and rename is overwritten.
- `atomic_write_text()` uses `mkstemp()`. Replacing a seeded `0664` config
  produces `0600`.
- Existing application code is unchanged during planning. Dirty state is
  limited to `.agents/ROADMAP.md`, `.agents/RELAY.md`, and new plan artifacts.

## Contract/API evidence

- Official `obsidianmd/obsidian-api` history commit
  `32fe4c3f4346d0b64fd5fdd5e25fc55f3a01c75a` adds
  `DataAdapter.process()` in the v1.1.0 API update.
- Current `plugin/manifest.json` declares `minAppVersion: 1.0.0`; current
  `plugin/versions.json` is absent.
- `SessionData.deletedSessionIds` and
  `ZoteroProfilesFile.deletedProfiles` already provide the required deletion
  semantics; no persisted schema change or migration is needed.
- No active scenario/testbed was selected and production state is out of scope;
  deterministic temp paths and memory adapters are sufficient for these three
  review regressions.

## Required red/green evidence

| Proof | Before fix | Required after fix |
|---|---|---|
| Stale nested project save | Peer-only key lost | Peer and requested keys survive; machine-local absent |
| Existing config `0664` | Becomes `0600` | Remains `0664` |
| New ordinary config | Forced `0600` | Matches normal umask-derived control |
| Secret key/store | `0600` after write | `0600` from temp creation through commit |
| Peer arrival before plugin callback | Peer data overwritten | Peer/local/tombstones merged |
| Callback corruption/interruption | Not covered | Exact canonical bytes preserved |
| Partial temp write | Temp may leak | Temp sibling removed |

## Validation record

- Pre-review release head: backend 1,382 passed / 6 skipped / 4 xfailed; Ruff,
  mypy, plugin build, 749 Vitest tests, version consistency, and GitHub CI green.
- Focused red phase: pending.
- Focused green phase: pending.
- Full local gates: pending.
- Latest-head GitHub CI: pending.

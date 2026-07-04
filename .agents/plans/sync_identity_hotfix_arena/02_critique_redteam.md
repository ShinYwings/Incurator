# Critique on Cache-Local Sync Bookkeeping
Date: 2026-07-04 | Agent Persona: red_teamer / schema_guardian

## 1. Vulnerabilities & Flaws

- A single global cache filename would collide across multiple vaults.
- Tests using temporary vaults could accidentally write into production cache.
- A new id alone is insufficient unless old JSONL files are imported as peers.
- Deleting the old shared JSONL before both new snapshots converge could lose
  the Linux-only four sources.
- Copying absolute vault paths into cache filenames would leak local paths.

## 2. Suggested Alternatives

- Hash the resolved vault root for namespacing and expose no absolute path in
  the filename or runtime payload.
- Monkeypatch `get_global_config_dir()` in every sync-state test.
- Add a regression test where both simulated devices begin with the same
  vault-local id, then use separate cache dirs and converge disjoint rows.
- Keep the old shared JSONL until both new snapshots have completed a round
  trip; remove only obsolete `sync_state.json`.

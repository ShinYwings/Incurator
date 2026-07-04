# Domain Analysis: Cross-Device Sync Identity

## Design Constraints

- Both backends may execute concurrently. Concurrent reads and writes to
  different source files are allowed; the same source file is not edited
  concurrently on both devices.
- `state.sqlite` is device-local and authoritative.
- `.curator/sync/dev-*.jsonl` is the only cross-device DB transport.
- One-writer-per-file requires a genuinely machine-local device id.
- `config.get_global_config_dir()` already defines backend-local
  `.cache/config`.

## Alternatives

1. Patch production `.stignore` only.
   Rejected because existing devices already share one id and future stale
   ignore files can recreate the failure.
2. Derive id from hostname/MAC while leaving marks in the vault.
   Rejected because peer high-water marks would still synchronize.
3. Store all sync bookkeeping in backend cache.
   Selected because identity and high-water marks become structurally local.

## Final Decision

```python
vault_key = sha256(str(internal_dir.parent.resolve()).encode()).hexdigest()[:16]
state_path = get_global_config_dir() / "sync_state" / f"{vault_key}.json"
```

The old vault-local state is not a fallback. On first v0.32.1 autosync each
device creates a new cache-local id and full snapshot.

The synchronization contract is:

1. each device writes only its own `dev-<device-id>.jsonl`;
2. Syncthing may deliver snapshots while the peer backend is reading;
3. each backend imports peer snapshots before using newly arrived state;
4. users avoid concurrent edits to the same source file/logical record.

# Backend Durable-State Review Domain Analysis

## Design constraints from repository reality

- `update_config_file()` already owns the per-path lock and supplies the YAML
  mapping read inside that lock. A second read or new locking layer is wrong.
- `save_config()` receives a full effective snapshot that may predate a peer
  update. `llm`, `search`, and `external` are machine-local routing keys and
  must never remain in `.curator/settings.yml`.
- `atomic_write_text()` serves both ordinary YAML and explicit credential
  storage. Replacement failure must leave canonical bytes intact and remove the
  temp sibling.
- Scope is POSIX permission bits only. Ownership, ACLs, xattrs, hard-link
  identity, and directory fsync are not added in this review fix.

## Authoritative invariants

- Existing corrupt/non-mapping YAML remains byte-identical and blocks mutation.
- Unrelated current top-level and nested project keys survive a stale save.
- Requested same-key values remain local-wins; omission is not deletion.
- Existing ordinary target mode is preserved; a new ordinary target receives
  `0666 & ~umask`; secret key/store files are exactly `0600` from creation.

## Alternatives and trade-offs

- Replacing the locked mapping with the stale snapshot is rejected because it
  reproduces the lost update.
- Three-way config merge is rejected because no base revision or tombstone
  contract exists. The additive unrelated-key policy is explicit and narrow.
- `mkstemp()` plus late `chmod` is rejected because it forces ordinary files to
  `0600` and can expose an explicitly private temp too broadly if generalized.
- Temporarily changing `os.umask()` is rejected because it is process-global.
  Secure `os.open(O_CREAT|O_EXCL)` lets the kernel apply the current umask.

## Final decision and pseudocode

```python
def _merge_project(existing, requested):
    current = deepcopy(existing)
    for key in MACHINE_LOCAL_CONFIG_KEYS:
        current.pop(key, None)
    requested = {k: deepcopy(v) for k, v in requested.items()
                 if k not in MACHINE_LOCAL_CONFIG_KEYS}
    return _merge_dict(current, requested)

def atomic_write_text(path, text, mode=None):
    try:
        preserved = mode if mode is not None else stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        preserved = None
    create_mode = preserved if preserved is not None else 0o666
    fd, temp = exclusive_random_sibling(path, create_mode)
    try:
        write(fd, text)
        if preserved is not None:
            os.fchmod(fd, preserved)
        flush_and_fsync(fd)
        close(fd)
        os.replace(temp, path)
    finally:
        close_if_open(fd)
        unlink_if_present(temp)
```

The new-file umask proof runs in a subprocess. POSIX mode assertions are
skipped on Windows; portable byte-integrity tests continue everywhere.

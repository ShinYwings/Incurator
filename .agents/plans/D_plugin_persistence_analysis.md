# Domain Analysis D — Plugin Sessions, Backend Secrets, And Runtime Snapshots

Date: 2026-07-30
Status: ACTIVE — input to regression-audit P6.
Confirmed findings: F14–F16.

## 1. Design Constraints And Invariants

- `sessions.json` is durable shared chat history and must merge across devices.
- Missing state and corrupt existing state are different conditions.
- A corrupt existing file must be preserved for recovery; it must never be
  replaced by an empty default on the next ordinary save.
- Writes of sessions, profiles, secrets, and global config must be serialized
  and atomic.
- Runtime snapshots are plugin-readable cache and must contain no plaintext
  credential, even when legacy config keys remain accepted for input.
- Device-local encryption does not excuse lost-update races in the encrypted
  store.

## 2. Confirmed Failure Modes

- `loadSessionData` catches missing and malformed JSON together; a later save
  overwrites corrupt history with the default in-memory state.
- `_read_store` converts malformed secret JSON into `{}`; the next
  `set_secret` destroys every prior credential. This was reproduced in a
  temporary directory.
- `_portable_status_config` shallow-copies the entire `llm` block, including
  supported legacy plaintext `api_key`.

## 3. Alternatives And Trade-Offs

### Automatic repair from empty defaults

Keeps the UI moving but silently destroys recoverable state and makes corruption
look like a legitimate empty account/session.

### Rename corrupt file and continue automatically

Preserves bytes, but may still create divergent synced state without telling the
user and can repeatedly fork corrupt copies across devices.

### Fail closed with explicit recovery and atomic writes

Differentiate ENOENT from parse/read errors. Missing files initialize normally;
existing corrupt files remain untouched and surface a concise recovery notice.
Valid writes use a temp sibling plus replace, and the secret store uses a
process lock around read/merge/write.

## 4. Final Decision

- Add typed parse outcomes: missing, valid, corrupt/unreadable.
- Session startup may fall back to legacy locations only when the canonical file
  is genuinely missing, not corrupt.
- Block canonical session writes after corrupt load until the file is repaired,
  restored, or explicitly preserved to a backup by a user action.
- Serialize and atomically replace session/secret/config files.
- Recursively redact key names matching credential semantics from runtime
  snapshots; preserve non-secret provider/model selection.
- Add crash/interleaving tests using temporary directories and mocked vault
  adapters.

## 5. Pseudocode

```text
read_state(path):
    if not exists(path):
        return Missing
    try:
        return Valid(parse_and_validate(read(path)))
    except ParseOrIOError as error:
        return Corrupt(error)  # never {}
```

```text
atomic_merge_write(path, mutate):
    with process_lock(path):
        current = require_valid_or_missing(path)
        next_value = mutate(current)
        write(temp_sibling(path), serialize(next_value))
        fsync(temp)
        replace(temp, path)
```

```text
redact(value, key_path):
    if normalized_leaf_key in {api_key, token, secret, password, credential}:
        return omitted
    recurse through mappings and arrays
```

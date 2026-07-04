# Backend Proposal: Cache-Local Sync Bookkeeping
Date: 2026-07-04 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

Compute a vault namespace from the resolved vault root and store bookkeeping at:

```text
<repo>/.cache/config/sync_state/<sha256(vault-root)[:16]>.json
```

`read_sync_state`, `write_sync_state`, and `get_device_id` keep their call
signatures. The synced transport remains:

```text
<vault>/.curator/sync/dev-<device-id>.jsonl
```

The old `<vault>/.curator/sync_state.json` is neither read nor converted. Each
backend therefore generates a fresh random id in its own cache and treats the
previous shared snapshot as a peer.

## 2. Pros & Cons

Pros:
- correctness no longer depends on `.stignore` upgrade hygiene;
- no SQLite or JSONL format change;
- current CLI/plugin callers remain unchanged;
- fresh ids trigger full snapshot exchange and natural LWW convergence.

Cons:
- moving or cloning a vault path creates a new local device id;
- the obsolete vault-local state file may remain until explicitly removed.

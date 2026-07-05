# Domain Analysis: Shared Plugin and Projection State

## Design Constraints

- Sessions and Zotero profiles are durable portable user state.
- Backend-generated Collections remain visible to Obsidian.
- Temporary plugin files must never enter the synchronized vault.

## Alternatives

- Treat all `.curator` files as local: rejected because sessions, profiles, and
  transport must sync.
- Single designated device writer: rejected because both devices may run and
  mutate distinct sources.
- Mergeable durable stores plus idempotent projections: selected.

## Final Decision

- Preserve sessions on backend reset and serialize session saves.
- Add explicit Zotero profile deletion tombstones and serialized saves.
- Put plugin CLI/PDF temporary files under repo `.cache` with no vault fallback.
- Keep per-record Collections in `.curator`; use atomic content-idempotent writes.
- Move dashboard, sync report, backend log, runtime, staging, and conflict
  archives to the machine cache.


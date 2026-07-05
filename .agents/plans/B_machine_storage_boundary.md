# Domain Analysis: Machine Storage Boundary

## Design Constraints

- All device-local state must live in the Incurator repository `.cache`.
- Vault `.curator` is synchronized and may contain only portable/shared state.
- Existing production has one `.curator/state.sqlite` that must not be lost.

## Alternatives

- Keep local files in vault and rely on `.stignore`: rejected because ignore
  upgrades do not reach existing vaults and the boundary is unenforced.
- OS home cache: rejected by the repository-local storage requirement.
- Repo cache keyed by resolved vault root: selected.

## Final Decision

Use `.cache/vaults/<vault-key>/` for DB, runtime, staging, reports, event log,
PDF caches/crops, and conflict archive. Write a local `vault_root` marker for
code that receives only a DB path. Relocate the old DB once; never fall back.

## Migration

```text
if old DB exists and new DB absent:
  backup old DB and sidecars under .cache/migrations/v0.32.1/
  move DB and sidecars to new cache
if old DB and new DB both exist:
  abort with explicit recovery instructions
```


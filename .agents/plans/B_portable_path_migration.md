# Domain Analysis B: Schema and Migration

## Current Reality

- DB schema version is 9.
- `sources.external_path` and `sources.import_origin` explicitly encode absolute
  paths.
- sync schema equality is already enforced in JSONL headers.
- production has one absolute source relpath and twenty dependent PDF-page rows.
- current cache root arrays are empty, but `/home/shin/Documents/Zotero` exists
  and contains the affected source; migration must still require a verified
  root match rather than assume from a username or filename.

## Alternatives & Trade-offs

- Add columns and leave old columns: rejected by the no-shim rule and leaves
  future callers able to reintroduce absolute values.
- Rebuild `sources` to v10: selected; more migration work but a clean contract.
- Rewrite values in place while retaining misleading names: rejected because
  `external_path` would continue to invite absolute paths.

## Final Decision

Rebuild `sources` with `external_ref` and `import_origin_ref`; preserve ids and
foreign keys. Perform config-aware conversion in an explicit migration service,
not in bare `db.connect()`. Repair reference `relpath` to a vault-relative stub,
rewrite dependent relpaths, clear/regenerate sync exports, and reject v9 peer
imports.

For a verified Zotero source, persist `logical_source_id =
zotero:<effective_attachment_key>` and leave both ref columns NULL. Use named
root refs only for generic external sources or Zotero-like legacy rows whose key
cannot be recovered.

Before apply:

```text
PRAGMA wal_checkpoint(FULL)
copy state.sqlite + sync exports -> <repo>/.cache/migrations/v0.29.0/<timestamp>/
preflight every legacy locator
```

After apply:

```text
PRAGMA foreign_key_check
PRAGMA integrity_check
scan every declared path-bearing DB field for absolute forms
export v10 JSONL
```

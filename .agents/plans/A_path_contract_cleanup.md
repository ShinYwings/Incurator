# Domain Analysis A: Path Contract Cleanup

## Design Constraints

- Current DB identity is `zotero:<attachment-key>` or
  `@<root_key>/<relative-path>`.
- Absolute roots belong only to repo-local `.cache/config/config.yml`.
- `state.sqlite` is device-local and does not receive another device's schema
  migration through Syncthing.
- Generic named-root resolution remains required current behavior.

## Alternatives & Trade-offs

1. Auto-run the migration from `db.connect()`: rejected as hidden backward
   compatibility and a write during read commands.
2. Keep `wiki paths migrate`: rejected because users should not manage an
   internal retired representation.
3. Drop all root-key logic: rejected because it is the current generic external
   reference contract.
4. Remove only retired input adapters: selected.

## Final Decision

The backend accepts and emits only schema-v11 source rows. The CLI exposes no
`paths` command. Config accepts only `external.path_roots` and Zotero
`root_keys`; legacy root arrays are ignored rather than converted.

## Implementation Pseudocode

```python
def resolve_source(source):
    if source.logical_source_id.startswith("zotero:"):
        return zotero.resolve_pdf(source.logical_source_id.key)
    if source.external_ref:
        return resolve_ref(source.external_ref, config.external.path_roots)
    return vault / source.relpath
```

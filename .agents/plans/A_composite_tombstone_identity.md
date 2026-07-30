# Domain Analysis A — Composite Tombstone Transport Identity

Date: 2026-07-30

## Design constraints from the current codebase

- `deleted_records` stores `(table_name, record_id, deleted_at)`.
- Six synchronized target tables use composite primary keys:
  `source_pages`, `source_pdf_pages`, `claim_supports`,
  `graph_relation_supports`, `entity_resolution_lineage`, and
  `artifact_dependencies`.
- `_apply_tombstone()` currently treats every `record_id` as one scalar. For a
  composite-key table it logs a warning, records the tombstone, returns success,
  and leaves the target row in place.
- `source_pages.source_id` and `source_pdf_pages.source_id` are replica-local.
  The existing row importer remaps them through `sources.sync_key`; a tombstone
  must make the same portability guarantee.
- SQL identifiers must come only from a closed table/key registry. Key values
  remain bound parameters.

## Spec invariants

- `state.sqlite` remains authoritative.
- A delete wins only when its `deleted_at` is newer than or equal to the
  competing row revision.
- Tombstone application is atomic with recording and statistics.
- The full primary key, including type, must survive a JSONL round trip.
- Missing, unknown, or ambiguous key fields fail closed. No delimiter-based
  concatenation and no best-effort partial `WHERE` clause are permitted.

## Alternatives and trade-offs

### Delimiter-joined strings

Rejected. Escaping is ambiguous, types are lost, and adding a key column later
breaks the parser.

### JSON arrays in physical primary-key order

Rejected. The meaning depends on external column order and is hard to inspect.
A schema reorder could silently target the wrong row.

### Rename `record_id` and rebuild `deleted_records`

Rejected for this release. The physical table already stores a transport token;
renaming the column adds a destructive table rebuild without improving delete
correctness.

### Table-specific canonical JSON object

Selected for composite keys. The object is self-describing, type-preserving,
reviewable, and can be validated against an exact per-table contract. RFC 8785
confirms the value of deterministic property ordering for stable wire identity;
this project uses a deliberately smaller domain of strings and integers and
Python's compact, sorted-key JSON output rather than claiming full JCS support.

References:

- [RFC 8785 — JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html)
- [SQLite foreign keys and composite keys](https://www.sqlite.org/foreignkeys.html)
- [SQLite row values](https://www.sqlite.org/rowvalue.html)

## Final decision

`SCHEMA_VERSION` becomes 13. `deleted_records.record_id` is the transport key
token:

- Single-key tables keep the existing raw portable identifier.
- Composite-key tables use compact sorted JSON:
  `{"key":{...},"v":1}`.
- The exact composite transport fields are:

| Table | Transport key fields |
|---|---|
| `source_pages` | `source_sync_key: str`, `wiki_path: str`, `at: str` |
| `source_pdf_pages` | `source_sync_key: str`, `page_number: int` |
| `claim_supports` | `knowledge_unit_id: str`, `source_span_id: str`, `support_role: str` |
| `graph_relation_supports` | `relation_id: str`, `knowledge_unit_id: str`, `support_hash: str` |
| `entity_resolution_lineage` | `decision_id: str`, `origin_entity_id: str` |
| `artifact_dependencies` | `artifact_id: str`, `depends_on_id: str`, `depends_on_type: str` |

For the two source-scoped tables, decode resolves `source_sync_key` to the
receiving device's local `sources.id` before constructing the parameterized
delete.

## Implementation pseudocode

```python
COMPOSITE_TOMBSTONE_KEYS = {
    "source_pages": (...),
    ...
}

def encode_composite_key(table, key):
    validate_exact_fields_and_scalar_types(table, key)
    return json.dumps(
        {"key": key, "v": 1},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

def decode_record_key(conn, table, token):
    if table has one transport key:
        return physical_pk_columns_and_values(token)
    payload = parse_and_validate_versioned_json(token)
    if "source_sync_key" in payload["key"]:
        source_id = resolve_local_source_id(conn, payload["key"]["source_sync_key"])
        replace_transport_field_with_physical_source_id()
    return physical_pk_columns_and_values()
```


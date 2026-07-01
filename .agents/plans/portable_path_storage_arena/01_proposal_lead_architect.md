# Backend Proposal: Named Portable Locator Boundary
Date: 2026-07-01 | Agent Persona: Lead Architect

## 1. Core Logic & Implementation

Use a two-tier portable identity:

1. Zotero-backed source: effective attachment key, persisted as
   `logical_source_id = zotero:<attachment_key>`. The backend queries the
   current device's Zotero DB and returns a runtime-only absolute path.
2. Generic external source: named-root locator using this canonical syntax:

```text
@<root_key>/<POSIX-relative-path>
```

Examples:

```text
@zotero_library/storage/ABCD/paper.pdf
@research_pdfs/Project/paper.pdf
```

Add a small backend `path_refs` module as the only conversion boundary:

```python
def encode_path(path: Path, roots: Mapping[str, Path]) -> str:
    # choose the longest containing root; reject if none contains path

def resolve_ref(ref: str, roots: Mapping[str, Path]) -> Path:
    # validate key, reject absolute/traversal path, join to configured root,
    # and verify the normalized result remains under that root
```

The machine-local config becomes:

```yaml
external:
  path_roots:
    zotero_library: /home/user/Documents/Zotero
    zotero_linked: /mnt/papers
  roots: [zotero_library, zotero_linked]
  zotero:
    enabled: true
    root_keys: [zotero_library, zotero_linked]
```

Persist portable refs in renamed source columns for generic external sources:

```sql
external_ref TEXT
import_origin_ref TEXT
```

`sources.relpath` remains strictly vault-relative and always points to the
Reference Mode Markdown stub for an external source. Runtime APIs may return a
resolved absolute path for an immediate open operation, but no persistence
writer may serialize that path.

For Zotero rows, `external_ref` and `import_origin_ref` are NULL. The effective
attachment key in `logical_source_id` plus the stub's portable Zotero link are
the complete locator. A parent item key received from a link is resolved to its
effective child attachment key before persistence.

Reference Mode rejects files outside configured roots with a structured
`root_unregistered` result. The UI then offers either root registration or
Copy Import. It never falls back to persisting an absolute path.

## 2. Pros & Cons

Pros:

- The DB and sync stream become portable without device-local merge exceptions.
- Zotero moves and cross-device root changes require no DB locator rewrite.
- One parser/resolver prevents each feature from inventing its own path logic.
- Longest-root matching handles nested Zotero and linked-attachment roots.
- Explicit rejection makes contract violations visible.

Cons:

- This is a breaking schema and plugin-state migration.
- Root keys must have the same semantic meaning on each device.
- Unregistered arbitrary download folders need an explicit setup step or copy.

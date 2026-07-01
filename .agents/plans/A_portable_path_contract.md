# Domain Analysis A: Portable Path Contract

## Design Constraints

- `.curator/` is synced/portable state and cannot contain device paths.
- `.cache/config/` is ignored, repo-local, and already hosts machine-local
  `external` configuration.
- vault files already have a natural root and use vault-relative POSIX paths.
- external Reference Mode files require runtime I/O without copying.
- Zotero DB already provides a portable attachment-key-to-file resolution
  authority, including linked attachments and parent-item keys.
- `logical_source_id` and content hash remain durable identity.

## Alternatives & Trade-offs

1. Keep absolute DB paths and hide them from payloads: rejected; this is the
   v0.28.5 behavior and violates storage portability.
2. Store plain relative paths from the vault (`../../Documents/...`): rejected;
   they are device-layout dependent and allow traversal.
3. Store only hash/logical id and rediscover on every open: rejected as the
   sole mechanism because generic external files may not have an external
   resolver and full-tree search is expensive.
4. Store named-root refs for all external sources: rejected for Zotero because
   it duplicates Zotero DB state, but selected for generic external sources.
5. Store Zotero effective attachment key only: selected for Zotero.

## Final Decision

Canonical Zotero locator:

```text
logical_source_id = zotero:<effective_attachment_key>
```

The backend resolves this key through the current device's Zotero DB whenever a
persisted view/source needs a physical path. The resolved path may be cached in
memory for the current config epoch but is never persisted.

Canonical generic external locator:

```text
@<root_key>/<relative-posix-path>
```

`root_key` matches `[a-z][a-z0-9_-]{0,63}`. The relative part must be nonempty,
must not begin with `/`, contain a drive/UNC prefix, or contain `.`/`..`
segments. Resolution joins against `external.path_roots[root_key]`, normalizes
the result, and verifies containment after symlink resolution.

Resolved absolute paths are transient values allowed only at I/O boundaries.
They must use distinct runtime DTO fields and are never passed to persistence
writers.

## Pseudocode

```python
def encode(path, roots):
    matches = [(key, root) for key, root in roots if path_is_within(path, root)]
    if not matches:
        raise RootUnregistered(path)
    key, root = max(matches, key=lambda item: len(item[1].parts))
    return PortablePathRef(key, path.resolve().relative_to(root.resolve()).as_posix())

def resolve(ref, roots):
    root = roots[ref.root_key].resolve(strict=True)
    target = (root / ref.relpath).resolve(strict=False)
    if not target.is_relative_to(root):
        raise PathEscape(ref)
    return target
```

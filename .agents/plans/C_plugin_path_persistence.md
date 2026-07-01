# Domain Analysis C: Plugin Persistence

## Current Reality

- plugin `data.json` supports device-specific backend/repo/Zotero path settings;
- external PDF localStorage entries persist `doc.path`;
- `ExternalPdfState.getState()` intentionally persists a resolved absolute path;
- session writing removes absolute `ContextRef.filePath` and `backendStatus`,
  but other structured path metadata needs an audited schema;
- arbitrary chat/source content can legitimately contain path examples and must
  remain byte-for-byte user content.

## Alternatives & Trade-offs

- Sanitize only when sync occurs: rejected; localStorage/workspace state can
  already contain and later resync stale paths.
- Recursively remove every absolute-looking string: rejected; corrupts prose.
- Typed portable persisted state plus memory-only runtime paths: selected.

## Final Decision

Persist external identity (`externalRef`, Zotero attachment key, hash, logical
id) and view metadata only. Resolve through backend on restoration. Remove
machine-local filesystem values from plugin settings persistence and route
them through backend `.cache/config/`. Validate all declared locator fields at
each write boundary and provide one migration that drops legacy absolute path
fields from data.json, localStorage, sessions metadata, and view-state inputs.

For Zotero, the effective attachment key is sufficient and `externalRef` is
omitted. Remove the plugin-side local filesystem resolver as a restore fallback;
backend Zotero DB lookup is authoritative. A process-local path cache remains
permitted and is invalidated when backend/Zotero configuration changes.

Tests cover POSIX, Windows drive, UNC, `file://`, traversal, stale macOS path on
Linux, and missing root variables.

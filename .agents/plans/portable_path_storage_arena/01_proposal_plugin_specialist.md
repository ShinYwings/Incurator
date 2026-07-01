# Plugin Proposal: Runtime Paths Are Memory-Only
Date: 2026-07-01 | Agent Persona: Plugin Persistence Specialist

## 1. Core Logic & Implementation

Separate portable state from runtime resolution:

- Zotero `ExternalPdfState` persists only effective `zoteroAttachmentKey`, hash,
  name, and view position. Generic external state persists `externalRef`; neither
  persists `path`.
- `externalPdfRegistry` persists the same portable identity in localStorage.
- a memory-only map holds resolved absolute paths for the current process.
- restored Zotero views must call the backend resolver with the attachment key.
  They must not use a saved path or plugin-side `~/Zotero` resolver fallback.
- restored generic views call the backend with `externalRef`.
- session sanitization recursively strips absolute values from known
  path-bearing metadata (`filePath`, backend status paths, revert filepaths,
  external PDF state) immediately before write.
- `zoteroBasePath`, absolute backend command/repo overrides, and other
  machine-local filesystem settings are removed from plugin `data.json`.
  Backend discovery remains memory-only; external roots are read or changed
  through backend config commands backed by `.cache/config/config.yml`.
- vault-relative plugin settings such as template, output, asset, and scroll
  paths remain relative and are validated before persistence.

At every persistence boundary, call a shared plugin validator that rejects
absolute values only in declared locator fields. Do not recursively alter
arbitrary message/source prose.

## 2. Pros & Cons

Pros:

- Obsidian Sync no longer transports device paths in plugin-owned metadata.
- External PDF tabs restore correctly on another device by identity.
- The backend remains the only authority for device-specific roots.
- Zotero DB remains the sole physical-path authority for Zotero attachments.

Cons:

- Restoring an unregistered PDF whose root is not configured becomes an
  actionable unresolved state instead of silently using a stale path.
- Removing path overrides changes the advanced settings UI.

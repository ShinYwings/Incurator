# Portable Path Storage Briefing
Date: 2026-07-01

## User Contract

Every filesystem locator persisted by the Obsidian plugin or anywhere under
the vault's `.curator/` tree must be portable:

- vault-owned files use vault-relative POSIX paths;
- Zotero files persist only the effective attachment key and resolve through
  the current device's Zotero DB;
- other external files use a relative path qualified by a named root variable;
- device-specific absolute root values live only in the Incurator repository's
  ignored `.cache/config/` backend configuration;
- backend code expands a named root variable to an absolute path only at an I/O
  boundary.

This includes SQLite, sync JSONL, generated Markdown, runtime JSON, plugin
`data.json`, plugin session metadata, plugin localStorage, and Obsidian external
PDF view state.

## Current Failure

v0.28.5 sanitized runtime snapshots but preserved the old storage contract:

- `sources.external_path` and `sources.import_origin` store absolute paths.
- `db_sync._preserve_device_local` treats `external_path` as a device-local
  exception instead of making it portable.
- a production legacy row also stores an absolute `sources.relpath`, copied to
  20 `source_pdf_pages.relpath` rows.
- `.curator/sync/*.jsonl` exports contain those values and can reintroduce them.
- `externalPdfRegistry` stores absolute paths in localStorage.
- `ExternalPdfState.path` persists absolute paths in Obsidian workspace state.
- plugin settings retain a separate `zoteroBasePath` instead of resolving the
  root through backend `.cache/config/config.yml`.

## Measured Production Evidence

Read-only inspection of `second_brain/.curator/state.sqlite` found:

- one reference source with absolute `relpath`, `external_path`, and
  `import_origin`;
- twenty `source_pdf_pages` rows carrying the same absolute relpath;
- a current sync JSONL containing absolute path fields in source rows;
- plugin sessions contain path-looking strings inside user/assistant prose and
  captured context text, but current structured `ContextRef.filePath` and
  `backendStatus` sanitization removes absolute path metadata.

## Required Design Questions

1. What is the canonical portable locator syntax and validation rule?
2. How are named roots configured and kept stable across Linux/macOS?
3. How are existing DB rows, sync exports, plugin caches, and view state migrated?
4. What happens when an external file is outside every configured root?
5. How do Zotero key/hash identity and human-approved rebind continue to work?
6. How is the invariant tested across every persistence boundary?
7. How do Zotero-backed views guarantee backend DB resolution on every restore
   without retaining the resolved absolute path as a fallback?

## Content Boundary Requiring Explicit Approval

The invariant applies to fields whose semantic purpose is a filesystem
locator. It must not rewrite opaque user-authored chat messages, source text,
LLM answers, or provenance previews merely because their prose contains a
string such as `/home/user/example`; rewriting source content would corrupt
knowledge. Structured path metadata embedded beside that content is in scope.

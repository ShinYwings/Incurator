# Critique on Portable Path Proposals
Date: 2026-07-01 | Agent Persona: Red Team

## 1. Vulnerabilities & Flaws

1. A raw `@key/path` parser can permit `../` traversal or symlink escape unless
   both lexical and resolved containment are checked.
2. Choosing the first matching root is unstable when roots are nested. The
   longest normalized containing root is required.
3. Deterministic names based only on array order can drift between devices.
   Migration-generated names are acceptable only as a local starting point;
   docs must require stable semantic root keys across devices.
4. Updating only `sources` leaves absolute paths in `source_pdf_pages`, sync
   exports, plugin localStorage, Obsidian workspace state, and possibly deleted
   record payloads or JSON text columns.
5. A blanket recursive string scrub would corrupt user messages, imported
   source text, code examples, and LLM answers. Validation needs a registry of
   locator-bearing fields, plus a separate diagnostic scanner.
6. Schema initialization currently applies migrations without `WikiPaths` or
   config context. A config-dependent data migration cannot be hidden inside
   a low-level `connect()` call.
7. Root registration from an arbitrary selected file's parent can create
   unstable or overly broad roots and leak more filesystem access than intended.
8. `external_ref` returned to the plugin is safe to persist; a resolved path
   returned for immediate opening is not. DTO types must make this distinction
   explicit to prevent accidental reserialization.
9. Stale v9 sync files must not merely be ignored locally while peers continue
   to export them. Schema mismatch must be clear, and every participating
   device needs v10 before autosync resumes.
10. Persisting a named-root ref for Zotero duplicates information already owned
    by Zotero DB and can become stale after Zotero/ZotMoov relocates a file. The
    effective attachment key must take precedence and leave locator columns NULL.
11. Plugin-side `resolveZoteroAttachmentPath("~/Zotero", key)` bypasses linked
    attachments, parent-to-child resolution, and backend configuration. Keeping
    it as a persistence fallback would preserve the same cross-device bug.

## 2. Suggested Alternatives

- Use a typed `PortablePathRef` value object and declared persistence schemas.
- Resolve symlinks and enforce descendant containment after joining.
- Keep root registration explicit and reject overbroad filesystem roots.
- Make v10 migration a top-level command receiving both `WikiPaths` and config;
  low-level DB code only performs schema rebuild after a complete conversion
  map is supplied.
- Back up DB and sync exports before mutation; remove backup files from the
  synced `.curator/` tree by placing them under repo `.cache/migrations/`.
- Add a repository test that scans serialized fixtures and all path-bearing
  schema fields for POSIX, Windows, UNC, and `file://` absolute forms.
- Require backend Zotero resolution on restore; allow a transient in-memory path
  cache only within the current process/config epoch.

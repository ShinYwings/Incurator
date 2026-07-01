# Schema Proposal: v10 Migration Without Legacy Path Shims
Date: 2026-07-01 | Agent Persona: Schema Guardian

## 1. Core Logic & Implementation

Bump `SCHEMA_VERSION` from 9 to 10 and rebuild `sources` atomically:

- replace `external_path` with `external_ref`;
- replace `import_origin` with `import_origin_ref`;
- preserve all other columns, ids, indexes, and foreign keys;
- add checks in application writes and migration tests rather than weak SQLite
  string checks that cannot validate a configured key.

Migration order:

1. Read machine-local named roots from `.cache/config/config.yml`.
2. Convert legacy root arrays to deterministic names (`zotero_library`,
   `zotero_2`, `external`, `external_2`) in the cache config.
3. Add discovered Zotero roots only when the legacy path is actually contained
   by the discovered root.
4. Preflight every absolute source locator. If any path has no matching root,
   abort before mutating the DB and report the exact source ids and the required
   root-registration command.
   Zotero rows are instead converted to key-only records when an effective
   attachment key can be verified from existing logical id/stub/DB metadata.
5. Create/repair a vault-relative Reference Mode stub for any reference row
   whose `relpath` is absolute.
6. Rewrite dependent `source_pdf_pages.relpath`, `source_spans.relpath`, and
   other source-linked relpath fields from the repaired source relpath.
7. Rebuild `sources`, run `PRAGMA foreign_key_check` and `integrity_check`, then
   stamp schema v10 in the same transaction.
8. Delete stale local sync export files and create a fresh v10 export. v9
   imports are rejected by the existing schema-version gate.

Zotero migration must not manufacture a generic root ref when a verified
attachment key exists. If a supposed Zotero row lacks a recoverable key, treat
it as a generic external source and require a named root.

Do not keep `_preserve_device_local` for source locators. Portable refs merge
normally and resolve against the receiving device's cache config.

Provide an explicit migration command with `--dry-run`, backup, and apply
modes. Automatic DB initialization may only apply v10 after preflight succeeds;
it must never blank or guess an unresolved locator.

## 2. Pros & Cons

Pros:

- Old absolute columns disappear rather than remaining an accidental API.
- Transactional preflight prevents partial corruption.
- Regenerated exports cannot reseed old absolute paths.

Cons:

- A device with incomplete root config must perform setup before migration.
- Repairing legacy rows without stubs requires deterministic stub creation and
  projection updates.

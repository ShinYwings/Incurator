# v0.29.0 Portable Path Storage Master Implementation Plan

Date: 2026-07-01
Status: APPROVED — User approved implementation on 2026-07-01.

## 1. Objective

Guarantee that every structured filesystem locator persisted by the plugin or
under `.curator/` is portable. Vault files use vault-relative paths. Zotero
files persist only their effective attachment key and resolve through the
current device's Zotero DB. Other external files use a named root reference
whose absolute root exists only in repo-local `.cache/config/config.yml`.
Migrate existing DB/plugin/sync state without losing source identity, PDF
provenance, view restoration, or Zotero rebind behavior.

Definition of done:

- no declared path-bearing field in `.curator/`, plugin data/localStorage, or
  Obsidian external-PDF view state contains POSIX, Windows, UNC, home-expanded,
  or `file://` absolute filesystem values;
- backend expands portable refs only in memory at I/O boundaries;
- the production legacy source and its 20 page rows migrate to a vault-relative
  stub plus named-root ref;
- v10 sync export/import works cross-device without `_preserve_device_local`;
- docs, EN/KR guides, tests, testbed smoke, versions, and changelog agree.

## 2. Explicit Non-Goals

- Do not copy Reference Mode files into the vault.
- Do not change content-hash or `logical_source_id` identity.
- Do not rewrite opaque user chat messages, source text, code examples, LLM
  answers, or text previews merely because the prose contains `/home/...`.
- Do not auto-register arbitrary filesystem roots from a selected file.
- Do not retain backward-compatibility reads of removed absolute DB columns.

## 3. Strict Quality Conditions & Release Gates

- `SCHEMA_VERSION` is 10; fresh and migrated schemas have identical columns.
- Migration is dry-runnable, transactional, idempotent, and aborts before write
  when any legacy locator lacks a configured/discovered root.
- Root-ref parser blocks traversal, symlink escape, unknown keys, absolute
  suffixes, Windows drive paths, UNC paths, and malformed refs.
- All persistence writers use declared portable DTOs; resolved paths are typed
  runtime-only values.
- v9 sync JSONL is rejected; migrated devices regenerate v10 exports.
- `PRAGMA integrity_check` and `foreign_key_check` pass after migration.
- Full backend pytest/ruff/mypy and plugin vitest/typecheck/build pass.
- Active testbed Reference Mode scenario passes before/after with external files
  remaining outside the vault.

## 4. Locked Design Decisions (Arena Consensus)

- Canonical external ref is `@<root_key>/<relative-posix-path>`.
- Zotero is key-only: persist `logical_source_id =
  zotero:<effective_attachment_key>` and leave external ref columns NULL.
- Zotero persisted views are restored through backend Zotero DB resolution;
  saved-path and plugin-side filesystem resolver fallbacks are removed.
- Canonical config is `external.path_roots: {root_key: absolute_root}` in
  repo-local `.cache/config/config.yml`; integrations reference keys, not paths.
- `sources.external_path` → `external_ref`;
  `sources.import_origin` → `import_origin_ref`.
- `sources.relpath` is always vault-relative and points to the stub for a
  Reference Mode source.
- One backend module owns encode/parse/resolve/validate logic and selects the
  longest containing root.
- External files outside all configured roots return `root_unregistered`; users
  explicitly register a root or select Copy Import.
- Absolute paths returned transiently for open/read operations cannot enter a
  persisted DTO.
- Plugin stores a Zotero key or generic external ref plus hash/view metadata;
  resolved paths live only in memory.
- Path invariants apply to structured locator fields, not opaque content.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: general storage quotas, PDF annotation architecture, and
  unrelated System Stability refactors.
- **Stop** if migration preflight cannot map every legacy source to a named root.
- **Stop** if repair would overwrite a user-authored `04_Resources` file.
- **Stop** if DB integrity/foreign-key checks fail; restore the cache backup.
- **P6 scenario**: `tests/scenarios/gaussian_splatting`, selected from the
  current production COLMAP/Gaussian Splatting source context.

## 6. Evidence Ledger

See `.agents/plans/06_roadmap_evidence.md`.

- Current production counts: one absolute source row and twenty dependent page
  rows.
- Current plugin persistence leaks paths through localStorage and view state.
- Current `.cache` external root arrays are empty; both common local Zotero
  directories exist, so migration must verify containment and register a
  semantic key rather than guess silently.

## 7. Execution Phases

### P0 — Approval, Backup, and Measured Baseline

- Confirm the structured-field versus opaque-content boundary.
- Confirm the active testbed scenario.
- Add a read-only `path audit` diagnostic and capture before counts.
- Back up production DB/sync files under repo `.cache/migrations/`.
- Verify: backup hashes and dry-run report; no production writes.

### P1 — Contract Specification

- Update all four static specs to v0.29 titles and define root refs, schema v10,
  DTO persistence rules, failure states, and migration.
- Update English guides first, then faithful `_KR.md` counterparts.
- Verify: spec sync and documentation link checks.

### P2 — Failing Contract Tests

- Backend tests: parser security, named-root config, ingest/rebind/status,
  fresh/migrated schema parity, dependent relpaths, v10 sync, stale v9 reject,
  and whole-DB path audit.
- Plugin tests: data.json sanitizer, sessions metadata, localStorage, external
  view state, mandatory backend Zotero resolution, cross-device resolution, and
  no-path fallback.
- Verify tests fail for the intended pre-change behavior.

### P3 — Backend Root References and Schema v10

- Implement typed portable refs and machine-local root mapping.
- Make Zotero attachment-key resolution the sole Zotero path boundary; persist
  no Zotero root-relative locator in source rows.
- Rebuild source schema and update all source/evidence/status/rebind paths.
- Remove `_preserve_device_local` source exception.
- Add dry-run/apply migration orchestration and clean v10 export regeneration.
- Verify targeted pytest + ruff + mypy and DB integrity checks.

### P4 — Plugin Persistence Boundary

- Replace persisted `path` with portable identity in external PDF registry/view.
- Remove persisted/local Zotero path fallback; restore Zotero views by key via
  backend DB lookup.
- Keep resolved paths memory-only.
- Remove filesystem-local plugin settings persistence and route root management
  through backend `.cache/config`.
- Migrate legacy plugin stores without retaining absolute fallback values.
- Verify vitest + TypeScript typecheck + production build.

### P5 — Production Migration

- Run dry-run against `second_brain`.
- Register/verify `zotero_library` in cache config.
- Apply once, inspect exact changed source/stub/page/export rows, then rerun
  idempotently.
- Run path audit across SQLite, JSON/YAML/JSONL, generated Markdown, plugin
  settings, sessions metadata, localStorage migration fixtures, and view-state
  serializers.

### P6 — Testbed Reference Mode Smoke

- Initialize the user-identified scenario with `wiki testbed init <scenario>`.
- Run `status`, `add`, `sync`, `lint`, and Reference Mode import/open/rebind.
- Verify the external fixture remains outside the vault and only its root value
  exists in repo `.cache/config/`.
- Restore any temporarily changed production path/config.

### P7 — Full CI, Release, and PR

- Run all mandated backend and plugin checks.
- Bump backend/plugin manifests to `0.29.0`; update all static spec title lines,
  changelog, roadmap, and RELAY.
- Remove implemented plan artifacts, create incremental commits plus final
  `chore(release): v0.29.0`, push, and open the PR.

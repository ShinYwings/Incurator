# Vault File Move & Delete Tracking

Status: approved decisions locked, ready to implement.
Source report: `.agents/USER_REPORT.md` (2026-08-06), ROADMAP item 3.
Branch: `feature/vault-file-move-tracking`. Target: **v0.46.0** (Minor — new CLI
surface and new plugin behaviour).

## Problem

Moving a file inside the vault after import breaks every stored reference to it.
The user hit it through the sidechat: after moving a Zotero-imported note from
`03_Notes/Vision/3DRec/` to `03_Notes/Papers/3DRec/`, an agent edit block came
back `⚠ File not found: 03_Notes/Vision/3DRec/3D Line Mapping Revisited.md`.

## Measured Reality (not assumed)

**The stale path is in no database column.** Checked the reported string against
every path-bearing column: `sources.relpath` 0 rows, `source_spans.relpath`
0 rows, `search_documents.projection_path` 0 rows. The reported symptom is
entirely plugin-side.

**The plugin subscribes to no vault file events at all.** Repo-wide there are
exactly two `registerEvent` calls, both workspace layout events
(`ChatSidebarView.ts:266,273`). No `vault.on("rename")`, no `vault.on("delete")`.
Obsidian supplies the old path on rename; nothing listens.

**The failure point is `resolveVaultFile` (`ChatSidebarView.ts:3921`).** Edit
proposals are parsed out of stored message text
(`extractMultiEditProposals(content, …)`), so the path lives in the persisted
conversation and goes stale silently.

**`resolveVaultFile` deliberately refuses a basename fallback**, and the comment
at `:3947-3949` gives the reason: *"a same-named file in a different folder is a
different note, and resolving to it would silently retarget the edit."* That
reasoning is correct and this plan does **not** weaken it. A rename journal is
exact provenance — "this file moved from A to B" — not a same-name guess, so it
resolves the case the comment was protecting against without loosening anything.

**The backend has no vault-internal move surface.** `wiki plugin source rebind
--new-path` looks like one and is not: `source_tools.rebind_source:372` writes
`relpath = row["relpath"]` — the OLD value — and only re-points `external_ref`.
It exists for an external PDF moving on disk. It also refuses `zotero:` sources
outright (`:352-358`).

**Three columns denormalize the path**, and `sources.sync_key` embeds it as
`vault:<relpath>` (verified against the live DB), so a move must update four
things, not one.

**Already rotting without any plugin involvement:** source 32 is registered at
`…-ref-5.md`, a path that exists nowhere; its 48 descendant atoms are exactly the
48 `invalid_source_path` errors that survive the v0.44.1 lint fix.

## Locked Decisions (user, 2026-08-06)

- **D1 — Delete marks, never destroys.** A deleted source file records
  `file_missing` and leaves L1–L4 knowledge and the graph untouched. `wiki lint`
  surfaces it; `wiki source rm` remains the explicit, user-driven way to retire
  the dependency closure. Rationale: an accidental Obsidian delete, or a file
  moved out and back, must not silently destroy extracted knowledge.
- **D2 — Zotero stubs are relocatable, logical identity survives.**
  `logical_source_id` (`zotero:KEY`) identifies the *document*; `relpath` is only
  where the vault stub sits. Moving the stub is a normal vault operation. The
  external PDF path stays Zotero-managed and is untouched — which is the real
  thing `rebind_source`'s `zotero_managed` refusal was protecting.

## Design

### Backend

1. **`db.relocate_source(db_path, source_id, new_relpath)`** — one transaction
   updating all four path carriers: `sources.relpath`, `sources.sync_key`
   (re-derived, not string-patched), `source_spans.relpath`, and
   `search_documents.projection_path` rows belonging to that source.
   **Preserves** `content_hash`, every layer status, `context_id`,
   `logical_source_id`, `is_reference`, and the whole derived closure — the
   content did not change, only its location.
2. **`db.set_source_file_missing(db_path, source_id, reason)`** — writes
   `error_reason='file_missing'` per D1. Uses `sources.error_reason`, which is
   already the free-text source-level reason column (`empty_file` is the existing
   precedent). No schema change, so no migration.
3. **CLI** (hidden plugin surface, matching the existing pattern):
   `wiki plugin source relocate --source-id|--from --to` and
   `wiki plugin source missing --from`.
4. **`wiki lint`** gains a check: a registered source whose `relpath` does not
   exist on disk. This is what surfaces D1's marker, and it also finally
   diagnoses source 32.

### Plugin

5. **`vault.on("rename")`** → append `{from, to}` to a persisted rename journal,
   then, if the old path is a registered source, call
   `wiki plugin source relocate`.
6. **`vault.on("delete")`** → call `wiki plugin source missing`.
7. **`resolveVaultFile`** consults the rename journal after its exact-path
   candidates fail and before returning null, following chains (A→B, B→C ⇒ A→C).
   The existing basename refusal stays exactly as it is.

## Phases

- **P1** — `relocate_source` + `set_source_file_missing` + tests.
- **P2** — CLI surface + `plugin_api` wiring + tests.
- **P3** — lint check for a missing registered source file + test.
- **P4** — plugin rename/delete events, journal, resolver + Vitest.
- **P5** — docs (SYSTEM_BEHAVIOR, SCHEMA, PLUGIN_SCHEMA, USER_GUIDE + `_KR`),
  v0.46.0 bump, spec titles to the v0.46 line, CHANGELOG.

## Explicitly Out Of Scope

Repairing vaults that already carry a dead row (source 32). The relocate path
fixes moves from here on; retro-repair needs a content-hash reconciliation sweep
and is its own item.

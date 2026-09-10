# Replica lifecycle proposal: Preserve retired audits after source removal
Date: 2026-09-10 | Agent Persona: Replica integrity reviewer

## 1. Core Logic & Implementation

The user's later exact error confirms the deterministic reproduction: current Mac snapshot `dev-28e419df29f2.jsonl` cannot import into a fresh schema-14 DB: `Table 'knowledge_units' references unmapped source_id 32`. Read-only inspection counted 62 retired knowledge units and one discarded compiler generation referring to absent source 32. The peer snapshot is 85 MiB, schema 14; the older peer snapshot is schema 12. No production data was changed. A temporary minimal DB using the CURRENT `_delete_source_on_connection` reproduces the same failure with source 1 in 30 ms: seed source and unit, delete source, export, import to fresh DB.

Root cause is a conflict between two otherwise valid contracts. `db/sources.py::_delete_source_on_connection` deliberately retains audit rows, marking units retired and generations discarded, but leaves their non-FK `source_id` referring to the removed row. `db_sync.py::export_knowledge` emits these values unchanged. `import_knowledge` correctly refuses to map a peer-local integer whose source was never exported. Source lifecycle tests check retention, but never removal → export → new peer → re-export. `query_traces` contains no scalar source_id and is not this failure; QTR recollection was superseded by the user's exact error.

Fix the lifecycle at the writer: when source deletion has finished querying its dependency closure, detach retained unit/generation `source_id` to NULL in the same deletion transaction, including units already retired before removal. Advance the same closure revision so LWW sees the detachment. Preserve row IDs, statement/evidence JSON, generation association/audit JSON and existing retirement timestamps; never delete retained audit rows. Do not detach early enough to break reconciliation queries that still filter the source ID.

A narrow import rule is also necessary: old snapshots already exist, and patching their files or asking users to regenerate them does not fix reopening an offline Linux peer. Pre-scan the actual source IDs present in the peer file. Only a knowledge unit with a valid nonempty retired_at, or a generation with status=discarded and valid discarded_at, may have its source_id detached when that parent is entirely absent from the peer. Preserve and import the audit row. Do not infer a mapping from the receiver's same numeric source ID. A parent omitted by --since but present locally is not enough evidence to reconstruct peer identity. An active unit, staged/authoritative generation, or malformed retirement remains a hard failure. A parent present later in malformed ordering must not be treated as absent. Existing source-tombstone blocking must remain authoritative; do not allow newer live rows through tombstones. Detachment on import is source-ID transport normalization, not a snapshot rewrite or a stored-data migration.

Export representation may normalize this same narrow condition for historical retained rows in the LOCAL DB so future exports carry portable nullable references; do not mutate the local DB or edit existing snapshots. However the lifecycle fix is mandatory and must stand alone: an output correction without fixing deletion would perpetuate the defect. Prefer one shared predicate for terminal audit rows; source existence must be checked against the complete source table/file, not the filtered --since subset. Invalid active orphans must remain visible.

The existing nullable schema suffices. Clarify that compiler generation NULL means corpus scope only for active generations; a discarded generation may instead have a removed source. Existing publication queries constrain authoritative status; verify this before broadening documentation. This is a synchronization semantic change and should be explicitly included in the parent's release plan. No production db migration, data cleanup, reset, reindex or snapshot-file edits.

## 2. Pros & Cons

This keeps all historical audit content while fixing the actual source lifecycle invariant and interoperating with peers that were offline during the bug. It avoids teaching the importer to accept arbitrary orphan data. NULL removes a meaningless device-local integer, but the historical source cannot be reconstructed safely from that integer alone. The test suite must assert unrelated receiver source IDs never get attached.

## 3. Tests and documentation

- Reproduction first: actual source removal preserves terminal audits with NULL source links, then export/import/re-export converges without rejected rows; include already retired units and an unrelated receiver source with the same integer ID.
- Imported source tombstone executes the same closure and remains re-exportable; preserve all existing deletion/serving tests.
- Historical retired orphan unit and discarded generation import successfully without changing the source file; whole audit payload survives other than source_id translation. Query traces/prompt refs also import and remain intact.
- Live orphan unit, staged generation, invalid timestamps, and parent later in malformed order still fail atomically. Ordinary partial exports do not silently detach live rows.
- Historical export normalization changes no DB rows, canonical file bytes, retirement clocks or peer IDs. Repeated imports are idempotent.
- Run source-lifecycle, DB sync, autosync, replica arbitration tests and isolated CLI smoke; replay real current snapshot into disposable DB for empirical verification, never a live vault.
- Update SYSTEM_BEHAVIOR sync/lifecycle, SCHEMA nullable audit scope, USER_GUIDE sync section English then Korean. Preserve auto-sync errors accurately; broad 'check repo path' appended to every failure is misleading and should be removed or confined to unresolved command errors.

## 4. Implementation and verification evidence

Implemented after master-plan synthesis on 2026-09-10. Documentation was updated before tests/code. Initial targeted regression run: 5 failed, 12 passed; failures were historical unit/generation import, export representation, and source-removal detachment. Final targeted run: 103 passed across `test_sync_terminal_audits.py`, `test_source_lifecycle.py`, `test_db_sync.py`, `test_db_autosync.py`, and `test_cli_db_autosync.py`; targeted ruff clean.

The implementation changes deletion at its end, after reconciliation, and reuses the existing import prescan to collect the complete peer parent inventory. Export uses the full local source inventory, never the `--since` subset. The predicate accepts only valid timestamped retired units/discarded generations. Tests exercise both terminal types, malformed/active/misordered parents, atomic rollback, receiver source 32 collision, unchanged snapshot bytes, unchanged local historical audit rows during export, repeated import, already-retired timestamps/revisions, and tombstone recipient re-export.

Real snapshot replay into a fresh disposable database completed in 3.99 seconds: 86,694 inserted, 54,274 tombstones, zero rejected. All 62 source-32 retired units and one discarded generation survived with detached source links; 123 query traces survived. Repeat import reported zero inserted/updated/deleted. Re-export succeeded (88,664,021 bytes). Original snapshot SHA-256 was unchanged. Existing provenance_dropped=120 was reported by the importer on this snapshot; this is separate pre-existing provenance handling, not silently relabeled by this fix. No live database was connected or changed during replay; the only real artifact read was the snapshot.

The plugin sync failure toast now preserves the backend cause without appending generic repository-path advice to data failures. Relevant guide EN/KR text is updated. No live database cleanup, migration, reset, reindex or snapshot-file rewrite was performed.

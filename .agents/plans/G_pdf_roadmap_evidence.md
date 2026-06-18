# Evidence Ledger — PDF Handling Unification (Plan G)

Date: 2026-06-19
Status: PRE-CODING. Populated during planning; P0 will append measured baselines.

## 1. Rollback Anchor

- Branch base: **`feature/agent-context-service`** (Plan F, committed checkpoint
  `3c05f08`). Plan G runs on `feature/pdf-unified-handling` branched OFF the F
  branch — a deliberate exception to the no-nesting convention, because Plan G's
  backend P2 (`pdf_identity.resolve()` routing `_locator_from_span`) depends on
  Plan F's `context_service.py`, which does not exist on `master`
  (verified 2026-06-19: `git cat-file -e master:.../context_service.py` → MISSING).
- Consequence: Plan G CANNOT be merged before Plan F merges. When Plan F merges
  to `master`, rebase `feature/pdf-unified-handling` onto updated `master`.
- No DB schema migration is planned (additive-only if any). Rollback = revert the
  feature branch; no data migration to undo.

## 2. Current Repository & Schema Reality (verified 2026-06-19)

- `sources` table carries: `relpath` (NOT NULL UNIQUE — the stub for Reference
  Mode), `external_path`, `import_origin`, `is_reference`, `logical_source_id`,
  `content_hash`, `file_type` (`backend/src/curator/db.py:83-110`).
- Reference Mode: in-vault markdown stub + `external_path` to the real file;
  both `add_file` and `generate_l1_structural_context` resolve the real PDF via
  `_resolve_reference_source` (verified — L1 is NOT poisoned by the stub).
- Locator: `_locator_from_span` labels reference PDFs `source_kind="vault_pdf"`
  with `external_uri` set; SYSTEM_BEHAVIOR §29.2 now states `external_uri` is
  authoritative for opening (updated this session).
- Spans carry their own `page_number` (`pipeline/source_spans.py:94,123`), so
  reference-PDF page locators resolve independently of `source_pdf_pages`.

## 3. Current Dirty Worktree (do not overwrite)

Plan F P6 work is uncommitted on `feature/agent-context-service`, including this
session's locator fix (`incuratorQueryTrace.ts` + 3 tests), the SYSTEM_BEHAVIOR
§29.2 / PLUGIN_SCHEMA / EN+KR guide clarifications, and the audit entry in
`USER_REPORT.md`. Plan G must branch off `master`, not bundle Plan F's diff.

## 4. Baseline Measurements (to be filled in P0)

- [ ] PDF module LOC total (baseline from 00_problem table = ~4570 plugin+backend
      PDF/Zotero LOC; record exact `wc -l` set).
- [ ] Backend dedup parity snapshot (reference/copy/zotero → `sources` rows).
- [ ] Persisted-doc rehydration characterization snapshot.
- [ ] Testbed E2E snapshot for the three flows.
- [ ] Item-3 repro attempt result (repro / cannot-repro → wontfix).

## 5. Rollback Requirements

- No destructive op before P4 (deletions). Each P4 deletion is its own commit so
  it can be reverted independently.
- Renderer extraction commits must keep `externalPdfView.ts` importable and the
  persisted-doc map intact at every step; a failed rehydration test halts P4.

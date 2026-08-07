# Incurator Active Roadmap

Updated: 2026-08-07

This file contains only live work. Completed milestones and planning artifacts
belong in Git history, not the active workspace. New raw reports enter through
`.agents/USER_REPORT.md`.

## Active Queue

Verified against the code on 2026-08-07, not against previous roadmap text.

### Shipped since the audits (v0.43.0 → v0.48.2)

Corroboration gate · B4 · `wiki lint` truthfulness · B3 P1–P4 · vault
move/delete tracking · the search-index support gate (61% of units were
unreachable) · language-independent routing, then corrected to enforce the
English-internal boundary at the backend · the workspace/curation lens on the
chat surface · entity-description prompt v2 · distant PDF equation references ·
the sidechat job indicator.

### 1. Formula recovery is built, specified, and never called

`pipeline/formula_recovery.py` implements `recover_formula()` and
`classify_formula_loss()`, SYSTEM_BEHAVIOR §26.2 specifies them, `compile.py`
imports and re-exports them — and there are **0 production call sites** against
14 test call sites (re-verified 2026-08-07). This is the remaining half of the
formula problem: v0.47.0 stopped the index from hiding unvalidated units, but
nothing repairs the PDF-extraction damage that made them unvalidatable.

### 2. `add source` stays clickable after a PDF is already added

Reported 2026-08-05 with the L3/L4 batch and **lost during a ROADMAP
restructure** — it was never tracked until now. After adding a PDF from the
purple pin the control remains enabled, so the same source can be submitted
repeatedly with no indication it is already in the knowledge system.

### 3. Community hierarchy is flat by construction

`_entities.py` hardcodes `level = 0`; one community holds 176 of 965 entities
while 152 of 233 are single-relation pairs. §27.4 permits the degraded
connected-components fallback but requires it be "surfaced by the audit" —
`config_hash` records it only as an opaque digest and `graph_audit` returns
violations only.

### 4. System Integrity Consolidation — the remainder

- **B2** (cross-device sync integrity) — the last P1 in the milestone.
- **B3 P5** synthesis dep-hash freeze · **P6** delete the dead L2
  checkpoint-resume (table migration) · **P7** record a reason on legitimate
  skips (needs a decision: `layer_error` is named for errors, `error_reason`
  already exists).
- **B5 / B7** each require their own Arena plan.
- Plan: `.agents/plans/03_system_integrity_consolidation.md`,
  ledger `03_b3_roadmap_evidence.md`.

### 5. `.curator` state audit — the remainder

- Losing `.cache/` reports a healthy **empty** vault: `connect()` self-heals a
  schema into any empty DB and `get_stats` returns zeros. Recovery exists (the
  in-vault sync journal + `wiki db import`) but is silent and undocumented.
- Vault rename/move silently mints a new empty DB (cache key is
  `sha256(resolved_root)[:16]`); also hits `VAULT_ROOT=testbed` from two
  directories.
- `sessions.json` 15 MB, **81% re-embedded context** — one note stored 52×, a
  1.39 MB base64 image, ~1.1 s per send. The 30-session cap is a provable no-op.
  Supersedes the old "Chat Session Context Compaction" draft.
- Sync journals never compact — 24 MB, `compress=True` exists unused with gzip
  measured at 9.86×; tombstones never expire; a stale peer is skipped silently
  while `autosync` reports success.
- `wiki sync` claims to rebuild `ledger.md`/`overview.md` and calls neither.
- `SYSTEM_BEHAVIOR.md` contradicts itself on where `state.sqlite` lives.
- Arena record: `.agents/plans/curator_state_arena/`

### 6. Retrieval and projection leftovers

- Span segmentation isolates single-word fragments
  (`pipeline/source_spans.py` splits on blank lines with no minimum length).
- One stale CTX file survives re-ingest (bounded — the index carries no CTX
  projection, so it cannot be retrieved).
- Retro-repair for vaults carrying a dead source row from a pre-v0.46.0 move;
  `wiki lint` reports them but nothing fixes them.

### 7. Job progress is unobservable

`ingest_worker.py` writes `progress=0.1` once when L2 starts and `0.5` only
after all of L2 returns; `progress_current/progress_total` stay `0/1` and
`job_events` gets zero rows. Reference-Mode jobs also display the `.md` stub
name for a PDF, and a running job cannot be cancelled.

### 8. Drafts not yet planned

- Vault Storage Governance & Quota Visibility —
  `.agents/drafts/vault_storage_governance.md`
- Native PDF Annotation & Asset System —
  `.agents/drafts/pdf_annotation_system.md`
- Web Search Integration — no current plan; re-plan from current provider,
  privacy, and cost constraints.

## Blocked / Icebox

- None.

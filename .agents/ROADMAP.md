# Incurator Active Roadmap

Updated: 2026-08-07

This file contains only live work. Completed milestones and planning artifacts
belong in Git history, not the active workspace. New raw reports enter through
`.agents/USER_REPORT.md`.

## Active Queue

Verified against the code on 2026-08-07, not against previous roadmap text.

### Shipped since the audits (v0.43.0 → v0.49.1)

Corroboration gate · B4 · `wiki lint` truthfulness · B3 P1–P4 · vault
move/delete tracking · the search-index support gate (61% of units were
unreachable) · language-independent routing, then corrected to enforce the
English-internal boundary at the backend · the workspace/curation lens on the
chat surface · entity-description prompt v2 · the sidechat job indicator ·
add-source state after ingest · Reference-Mode sources resolved by Zotero
identity · unresolved cross-references named instead of dropped ·
**image-only extraction loss made visible** (v0.49.0/.1).

Note: v0.48.1 "distant PDF equation references" shipped but was a **no-op** —
see item 1. It searched neighbouring pages for a label that was never ingested.

### 1. Formula RECOVERY — blocked on three prerequisites, not on a plan

Visibility shipped in v0.49.0/.1: `source_spans.metadata.loss`, a `wiki lint`
`extraction_loss` check, a `wiki add` warning, and an `[image-not-extracted]`
marker that survives into the L1 projection the plugin reads. On the reporting
vault that surfaces **130 unreadable regions across 4 sources** (95 of them in
one 27-page paper). The assistant now says which region it could not read and
why. **It still recovers nothing.**

`recover_formula()` and `classify_formula_loss()` remain at **0 production call
sites**. The Arena (`.agents/plans/formula_recovery_arena/`) established that
wiring them today yields an estimated **0–2 of ~48 regions** — a third no-op —
because three things are missing. Any recovery plan must start here:

1. **The acceptance gate rejects faithful transcriptions.**
   `formula_recovery.py:135` uses token-tuple **equality**
   (`recovered_tokens in claim_formulas`) where `validate_claim_support` uses
   **subsequence** (`_is_formula_subsequence`, `claim_support.py:343`). Of 8
   plausible faithful transcriptions of `KNU-63af4c5c`'s formula, 6 reject —
   `^\top` vs `^{T}`, `\boldsymbol{\lambda}` vs `\lambda`, a `\tag{26}`.
2. **`validator_trace_id` has no producer.** Every occurrence in the backend is
   a parameter, a pass-through, or a column read. Nothing mints one, so the
   `reviewed` state is unreachable and every candidate would sit at
   `candidate` forever.
3. **The region cannot be cropped.** `recover_formula` wants a `crop_hash` and
   locator; placeholder spans carry `metadata = None`, and the only geometry
   that survives is `[width x height]` in the placeholder text — no page
   coordinates. `page_number` is a section index, not a physical page (max 23
   on a 27-page PDF).

Useful anchor for whoever picks this up: the user's own question maps to
`KNU-63af4c5c` (`formula_status='uncertain'`), whose cited span
`SPAN-6df340cb` on p11 reads "This is a quadratic equation in λ1 and λ2, and
can thus be written as" — and whose rowid±1 neighbours are **both** placeholder
images. 159 of 480 `uncertain` units vault-wide (99 on source 37) sit adjacent
to a placeholder, so the owning claims already exist; what is missing is a
locator, not a unit.

### 2. Community hierarchy is flat by construction

`_entities.py` hardcodes `level = 0`; one community holds 176 of 965 entities
while 152 of 233 are single-relation pairs. §27.4 permits the degraded
connected-components fallback but requires it be "surfaced by the audit" —
`config_hash` records it only as an opaque digest and `graph_audit` returns
violations only.

### 3. System Integrity Consolidation — the remainder

- **B2** (cross-device sync integrity) — the last P1 in the milestone.
- **B3 P5** synthesis dep-hash freeze · **P6** delete the dead L2
  checkpoint-resume (table migration) · **P7** record a reason on legitimate
  skips (needs a decision: `layer_error` is named for errors, `error_reason`
  already exists).
- **B5 / B7** each require their own Arena plan.
- Plan: `.agents/plans/03_system_integrity_consolidation.md`,
  ledger `03_b3_roadmap_evidence.md`.

### 4. `.curator` state audit — the remainder

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

### 5. Retrieval and projection leftovers

- Span segmentation isolates single-word fragments
  (`pipeline/source_spans.py` splits on blank lines with no minimum length).
- One stale CTX file survives re-ingest (bounded — the index carries no CTX
  projection, so it cannot be retrieved).
- Retro-repair for vaults carrying a dead source row from a pre-v0.46.0 move;
  `wiki lint` reports them but nothing fixes them.

### 6. Job progress is unobservable

`ingest_worker.py` writes `progress=0.1` once when L2 starts and `0.5` only
after all of L2 returns; `progress_current/progress_total` stay `0/1` and
`job_events` gets zero rows. Reference-Mode jobs also display the `.md` stub
name for a PDF, and a running job cannot be cancelled.

### 7. Drafts not yet planned

- Vault Storage Governance & Quota Visibility —
  `.agents/drafts/vault_storage_governance.md`
- Native PDF Annotation & Asset System —
  `.agents/drafts/pdf_annotation_system.md`
- Web Search Integration — no current plan; re-plan from current provider,
  privacy, and cost constraints.

## Blocked / Icebox

- None.

# Incurator Active Roadmap

Updated: 2026-08-10

This file contains only live work. Completed milestones and planning artifacts
belong in Git history, not the active workspace. New raw reports enter through
`.agents/USER_REPORT.md`.

## Active Queue

Verified against the code on 2026-08-07, not against previous roadmap text.

### Shipped since the audits (v0.43.0 → v0.55.0)

Corroboration gate · B4 · `wiki lint` truthfulness · B3 P1–P4 · vault
move/delete tracking · the search-index support gate (61% of units were
unreachable) · language-independent routing, then corrected to enforce the
English-internal boundary at the backend · the workspace/curation lens on the
chat surface · entity-description prompt v2 · the sidechat job indicator ·
add-source state after ingest · Reference-Mode sources resolved by Zotero
identity · unresolved cross-references named instead of dropped ·
**image-only extraction loss made visible** (v0.49.0/.1) · **all five of B2's
sync-integrity items** (v0.49.2 conflict-archive EXDEV, v0.49.3 export-stamp
race, v0.50.0 truthful import outcome, v0.50.1 single-source trigger
definitions, v0.50.2 locked device-state RMW) — B2 is closed — and **B3 P5**
(v0.51.0 truncated-L4 detection) · **v0.53.1** agy permission-rule fix (the
allow-rule was pruned on every run, causing "jetski: no output produced" on
headless CLI calls) · **v0.53.2** chat sidebar `fetchPageText` viewer fallback
(Zotero / untracked PDFs now resolve distant cross-references without backend).

**v0.53.2–v0.55.0 — the reading-assistant line** (item 11, now closed, plus the
prompt defects the same investigation surfaced):

- **v0.53.2** popover grounding relaxed + sidechat pinned sources injected into
  the popover, within the `local-only` boundary. Shipped straight to master with
  no PR; reviewed retrospectively during the v0.53.0→v0.55.0 pass, which is
  where the two defects below came from.
- **v0.53.3** (#152) the three prompt sites that *instructed* the model to
  narrate its own retrieval state ("say you could not retrieve the referenced
  item") are gone. The user was seeing that narration instead of an answer.
- **v0.54.0** (#153, plan P0) the system prompt now opens with the assistant's
  three duties — read alongside, remind of prior notes, find new value —
  instead of a wall of prohibitions. Duty 3 had **zero** instructions anywhere
  in the stack before this. Budget gated at 17,000 chars / 23 negatives.
- **v0.54.1** (#155) the `ANTIGRAVITY_*` scrub, which v0.53.2 recorded as
  shipped "across the entire repo" but had only applied to the plugin. The
  backend half was written, left uncommitted, and shipped to nobody, so every
  `wiki`-driven `agy` spawn stayed hijackable by the host IDE daemon.
- **v0.55.0** (#154, plan P2) `read_pdf_page_image` — renders any page
  off-screen and reads the pixels, so a rasterized equation answers without the
  user snipping it. Model-invoked, not heuristic: `isScannedLike` is a
  whole-page aggregate and the page holding the equation measures 4,193 text
  chars, so no threshold can see the picture region.

Two master-level defects fixed by fast-forward along the way: hatchling 1.30
rejecting the backend package metadata (backend CI had gone red with no commit
causing it), and **the version-consistency gate that had never once run on a
pull request** — its condition tested `github.ref` against `refs/heads/*`, which
is never true for a `pull_request` event. That is how v0.53.2 shipped with the
backend at 0.53.1 and the plugin at 0.53.2.

Note: v0.48.1 "distant PDF equation references" shipped but was a **no-op** —
see item 1. It searched neighbouring pages for a label that was never ingested.

### 1. Formula RECOVERY — BUILT AND TESTED, BUT NEVER INVOKED

**Status corrected 2026-08-14 by reading the code.** This item said "blocked on
three prerequisites". That is no longer what is wrong with it.

`backend/src/curator/pipeline/formula_recovery.py` exists (commit `1f9a088`,
"feat(pipeline): add selective formula recovery"), exports `recover_formula`,
`classify_formula_loss`, and `invalidate_formula_recoveries`, and is covered by
`test_plan_b_formula_recovery.py` — **6 tests, all passing**. The
`validator_trace_id` producer this item listed as a missing prerequisite exists
too, at `formula_recovery.py:226`.

`pipeline/compile.py` imports all three symbols — **only to re-export them in
`__all__` (line 56)**. Grepped across the whole backend: `recover_formula(` is
never called. The single hit outside its own definition is a comment in
`db_sync.py:149`.

So the work is not blocked. It is finished and disconnected. The remaining task
is wiring it into the compile path and deciding when it runs, which is a much
smaller and much better-defined job than the one this item described.

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

- **B2 — COMPLETE** (v0.49.2 → v0.50.2, all five items). The milestone has no
  P1 left; everything below it is P2/P3.
- **B3 P5 — DONE** (v0.51.0): a truncated L4 layer is detected instead of
  frozen as complete. **P6** delete the dead L2 checkpoint-resume (table
  migration) · **P7** record a reason on legitimate skips — **blocked on a user
  decision**: `layer_error` is named for errors and `error_reason` already
  exists, so which column carries a non-error reason is a contract choice, not
  an implementation detail.
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

### 5. `graph_entities` / `source_spans` transport on a surrogate id

Both carry a natural identity — `UNIQUE(canonical_name, entity_type)` and
`UNIQUE(source_id, content_hash)` — but sync transports them on the surrogate
`id`, so two devices that independently extract the same thing mint different
ids. The key lookup misses, the insert collides on content, and convergence has
to be classified after the fact (v0.50.0 does this via `PRAGMA index_list`).
`sources` solved the same problem properly with a `sync_key` transport identity,
so the primary lookup finds converging rows directly and children remap to the
local id.

Nothing remaps `graph_relations.source_entity_id`/`target_entity_id` when an
entity converges, so the classifier makes the symptom quiet without closing the
gap. The real fix is a transport identity for both tables plus the id-remap
plumbing — a schema change touching every referencing column, which is why it
was left out of v0.50.0 rather than smuggled in.

### 6. Resumable L2 extraction — wanted, needs designing

Removed in v0.51.1 rather than repaired (B3 P6). The old mechanism could never
run: checkpoints were written only inside the branch that required checkpoints
to already exist, so `l2_checkpoints` held 0 rows across 36 sources and 2,799
units. Deleting it changed no behavior.

The cost it was meant to avoid is real. An interrupted L2 build restarts from
the first batch, so a 40-batch source re-pays every provider round-trip — at the
measured 8–12 s per CLI round-trip that is 5–8 minutes per retry.

It must be designed, not re-enabled. The removed branch returned
`list_staged_unit_ids_for_source`, which filters `generation_id IS NULL` and is
therefore **empty after a successful publish** — a resumed run would have
attributed zero units to a fresh generation and retired the source's entire
authoritative unit set under §26.3. Any new design has to decide what a resumed
run returns, and how a partially-published source is distinguished from an
unstarted one.

### 7. Retrieval and projection leftovers

- Span segmentation isolates single-word fragments
  (`pipeline/source_spans.py` splits on blank lines with no minimum length).
- One stale CTX file survives re-ingest (bounded — the index carries no CTX
  projection, so it cannot be retrieved).
- Retro-repair for vaults carrying a dead source row from a pre-v0.46.0 move;
  `wiki lint` reports them but nothing fixes them.

### 8. Job progress is unobservable

**Status corrected 2026-08-14 by reading the code. Mostly resolved; one
sub-item survives.**

- ~~`progress=0.1` once when L2 starts and `0.5` after all of L2~~ — resolved.
  `WorkerCallbacks` (`ingest_worker.py:39`) reports 0.25 / 0.5 / 0.75 / 0.9
  across `on_pass1_start`, `on_fragment_written`, `on_pass2_start`,
  `on_theme_written`.
- ~~`progress_current/progress_total` stay `0/1`~~ — resolved. Written with
  real `pages_seen` values at lines 54–86.
- ~~a running job cannot be cancelled~~ — resolved. `db/jobs.py:243
  cancel_job`, with `STATUS_CANCELLED` surfaced through `runtime_state.py`.
- ~~`job_events` still gets zero rows~~ — resolved in v0.58.0 (#159).
  `db/job_events.py` inserts, `ingest_worker.py` calls it from the same
  callbacks that write progress, and `wiki jobs events <id>` reads it back
  oldest-first. It lives in its own module because `db/jobs.py` and
  `db/__init__.py` are content-hash-pinned in `D2_HOLDOUT_RESULT.yml`.
  Note the rows are new from v0.58.0 onward: jobs that ran before it have no
  history and will read as empty, which is expected rather than a regression.
- Reference-Mode jobs displaying the `.md` stub name for a PDF: not re-verified
  in this pass.

### 9. Drafts not yet planned

- Vault Storage Governance & Quota Visibility —
  `.agents/drafts/vault_storage_governance.md`
- Native PDF Annotation & Asset System —
  `.agents/drafts/pdf_annotation_system.md`
- Web Search Integration — no current plan; re-plan from current provider,
  privacy, and cost constraints.

### 10. PDF whole-document search — PLANNED, awaiting approval

`pdfFullDocumentIndex` ("Background page indexing") has **0 consumers** — the
toggle writes a value nothing reads, so `search_pdf_anchor` can only find
content on pages already rendered. The chat can read any page it can *name*
(`fetch_pdf_page`) but cannot *locate* one.

Arena concluded: `.agents/plans/pdf_background_index_arena/`
Master plan: `.agents/plans/04_pdf_background_index.md` (v0.54.0)

Two defects the Arena verified, both of which must be fixed before any walk:
- `upsertPage` is **quadratic** — 226,801 tokenize calls for 673 pages (337x).
- A naive `notifyContextChanged()` progress tick cascades into an unconditional
  main-thread BM25 search + chip rebuild, ~27 times per book open.

### 11. Backend `agy` spawn has no OS sandbox (opened by v0.56.1)

`AntigravityCliClient._run` (`backend/src/curator/llm.py`, the Antigravity
client) spawns `agy` with plain `subprocess.run` — no sandbox wrapper, unlike
`CodexCliClient`, which passes `--sandbox read-only`. It also sets
`ANTIGRAVITY_TRUST_WORKSPACE` / `AGY_TRUST_WORKSPACE`.

This was latent while the read permission was broken. v0.56.1 fixed that
permission (it had to — the vision path was dead without it), so the backend
now spawns an unsandboxed CLI that can read any file the user can, on the code
path that processes **ingested, untrusted source material**. The trade was
taken deliberately and is recorded in PLUGIN_SCHEMA §13.5 and in both plugin
guides.

**Be clear about what fixing this buys.** The existing sandbox
(`sandboxWrapper.ts`) is a *write* sandbox: macOS Seatbelt is `(allow default)`
+ `(deny file-write*)`, and Linux bwrap read-only-binds the whole filesystem.
Applying it to the backend aligns the two spawn paths and adds write and
process containment — it does **not** close the read exposure, because reads
were never restricted on either path (`sandboxWrapper.ts:19`: "Reads are
intentionally still allowed (denying reads breaks the CLI's…)").

So this item is worth doing as hardening, and MUST NOT be filed as "the fix for
the v0.56.1 read grant". Closing that would need a read-restricted profile with
an allowlist of everything agy needs — designable, but it breaks on every agy
release, which is why it was not attempted here.

The exposure is bounded by what else is granted: exactly `read_file(*)` and
`command(wiki)`, with unapproved tools auto-denied in headless mode. No write
tool, no arbitrary shell, no network tool. Realistic worst case is a secret
read into the user's own vault, not remote exfiltration.

Eliminating it entirely is a configuration choice, not a code change: a vision
model reached over an API takes image bytes directly and needs no filesystem
grant. Recommended in both guides.

## Blocked / Icebox

- None.

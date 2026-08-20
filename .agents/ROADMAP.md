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

**v0.53.2–v0.55.0 — the reading-assistant line** (the reading-assistant item, now closed, plus the
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

### Recently shipped (moved out of the queue)

- **v0.59.0 (#160) — job progress emitted from the loop that runs.** v0.58.0 had
  attached the writer to `WorkerCallbacks`, which an L2 job never invokes.
  Remainder: **the L3 phase still has no per-step heartbeat**, because
  `run_l3_from_existing_atoms` accepts a callbacks factory and never calls it.
- **v0.60.0 (#162) — the CLI is asked for a value, not for prose.** Nicholson
  (died at batch 9/15) completes; Hartley (died at 37/277) extracts 277/277 with
  zero permission denials. The schema must be flattened: unflattened, agy returns
  SUCCESS with an empty structure and the answer in prose, so every book would
  ingest to nothing while reporting success. Hartley is still not ingested — a
  429 at publish, then a folder-permission wall (item 3).

### 1. Formula RECOVERY — BLOCKED ON LOCATING THE REGION, and on item 2

**Arena concluded 2026-08-20 with no build.** `.agents/plans/formula_recovery_arena/`
(`00_problem_v2.md` … `04_conclusion.md`). Five measurements removed every
premise the plan would have been written against, so the output is this
corrected item rather than a phase list.

`pipeline/formula_recovery.py` exists, exports `recover_formula`,
`classify_formula_loss`, `invalidate_formula_recoveries`, and has 6 passing
tests. `pipeline/compile.py` imports all three **only to re-export them**.
`recover_formula(` has **0 production call sites**.

**Wiring it today recovers 0 regions**, and not for the reasons this item used
to give. It cannot locate one:

- **0 of 2,121** loss regions carry page coordinates. All carry
  `{width, height}` and nothing else.
- The coordinates are not discarded — the parser never has them.
  `pymupdf4llm` emits `**==> picture [185 x 12] intentionally omitted <==**`
  and `source_spans.py:72` parses the size out of that string.
- They cannot be re-associated afterwards. Size join: **6 of 1,135**. Per-page
  positional join (k-th marker ↔ k-th image): **3 of 158**.
  `get_image_info` reports vector drawings too, so one page carries 5 markers
  against 36 image objects — the two lists describe different populations.

**Corrected numbers.** This item said "130 regions across 4 sources"; the vault
stores 1,135 across **3**, and the *current* parser finds **2,121** (437 + 11 +
1,673). The original Arena's "~48 regions", against which it estimated 0–2
recoveries, was low by a factor of forty.

**Corrected blocker order.** Blocker 3 is not a prerequisite alongside the other
two — it is the milestone, and it lives in parsing rather than in recovery code:

1. **Acceptance gate.** `formula_recovery.py:135` uses tuple equality where
   `validate_claim_support` uses subsequence. Measured on 8 faithful
   transcriptions: equality accepts 2, subsequence accepts **5**. The three that
   still fail differ in tokens, not span — `^\top` vs `^{T}`, `\boldsymbol` vs
   `\mathbf`, `\left…\right` sizing — so swapping the comparison is only half
   of it and notation normalisation is a contract question.
2. **`validator_trace_id` has no producer.** Every occurrence is a parameter, a
   pass-through, or a column read; the only non-`None` values in the repo are
   test fixtures. `reviewed` is unreachable. (This item's header previously
   claimed the producer existed at `:226`, contradicting this line. Corrected
   2026-08-20.)
3. **The region cannot be located.** See above. This is the gate.

**What would reopen it**: one cheap experiment — does `pymupdf4llm` expose the
association between an omitted-picture marker and the image object it stands
for? Yes → blocker 3 becomes tractable. No → the question is whether the
pipeline should stop using its markers and walk the page with `fitz`, which
needs its own briefing.

**Also blocked on item 2**: every number above that comes from `source_spans`
describes an older parse.

### 2. A source whose parse improved is never re-derived

`l2_status='done'` means a source is never re-parsed, so **a shipped parser fix
reaches only sources ingested after it**.

Measured on source 37: **646 spans stored, 2,050 computed from the same PDF
today**, and **4** loss records stored against **437** the current parser finds.
It was added 2026-08-04; v0.49.0 taught the parser to report unreadable regions
on 08-08. It has never seen that improvement and never will.

Consequences beyond one source:

- Every stored measurement is a claim about whatever parser ran when that source
  was last ingested, and nothing says so at the point of reading. This is how
  ROADMAP 1 came to be scoped against a count that was wrong by 40×.
- A parser improvement silently splits the corpus into sources that have it and
  sources that do not, with no surface reporting the split.

Not designed. The obvious approach — record the parser/contract version on the
source and re-derive when it moves — is a schema and cost question
(re-parsing the 673-page book takes 79 s; the whole vault is unmeasured), so it
needs a plan rather than a patch.

**This is upstream of item 1** and should be settled first.

### 3. ~~External-file access cannot tell "missing" from "not allowed"~~ — SHIPPED v0.61.0 (#163)

`probe()` opens the file, because `os.access(R_OK)` returns **True** for a
TCC-denied one — the audit's own proposed fix would not have worked. A denial
now reports as `attachment_file_denied` with the folder to grant, found by
probing ancestors rather than matching a table of macOS locations. `wiki status`
lists affected sources once; on the live vault it found four, not the one that
prompted the work.

Review caught three things worth remembering:

- **The plugin consumes this taxonomy and was not updated**, so the new state
  showed the user a raw enum string. The states and that `switch` were born in
  the same commit; they move together.
- **A documented invariant was broken silently.** XC-1 established that
  `_resolve_reference_source` degrades on any failure; the denial carve-out is
  correct but no plan document acknowledged it. The test docstring now states it.
- `grant_root` stopped at the first *listable* ancestor. Listing and reading are
  different macOS checks, so it returned nothing for exactly its own use case.

**Remainder**: the plugin's own read path (`ExternalPdfView.ts:1385`) still goes
`existsSync` → `readFileSync` and surfaces a raw Node error. No folder picker
and no permission request — macOS has no API, and the open question is whether a
grant obtained by Obsidian reaches the separately spawned backend.

### 4. System Integrity Consolidation — the remainder

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

**Its inventory lives in `system_defect_audit_arena/03_synthesis.md`** — the
B-batches this item tracks are that synthesis's batches, so the two are one
piece of work, not two. That folder was briefly deleted as "finished" and
restored; it is unreadable as status because nobody has walked it item by item.

Sampled against current code (numbers are the SYNTHESIS's, not this
roadmap's): its item 10 (`recover_stale_jobs` NULLing
`layer_error`) is **fixed** — the prescribed `CASE WHEN` guard is at
`db/jobs.py:171`; its item 13 (`wiki sync` promoting `l3/l4_status` from a glob) is
**fixed**, its docstring says "It used to also promote"; the synthesis's two
"never ran" domains later did run (`04_g0_exception_hygiene.md`,
`04_g0_docs_parity.md`). `knowledge_value_arena/` has had no triage at all.

**P6 is DONE, not pending** — the dead L2 checkpoint-resume was deleted in
v0.51.1, which is what item 5 (resumable L2) picks up from. The line below
saying otherwise was stale.

**NEXT here**: one pass per inventory item recording shipped/open, then delete
the folders. Not before — that ordering is what went wrong once already.

### 5. Resumable L2 extraction — wanted, needs designing

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

**Measured cost, 2026-08-19**: Hartley completed **all 277 extraction batches**
and then hit a 429 at publish. All-or-nothing discarded every batch — about 90
minutes. This is the sharpest case this item has: not "interrupted midway" but
"finished the expensive part and threw it away". Continues ROADMAP 4's P6.

**PLANNED, awaiting approval (2026-08-21)** — `.agents/plans/06_resumable_l2.md`,
Arena at `.agents/plans/resumable_l2_arena/`. The question above ("what does a
resumed run return?") is answered by D5. The design needs **no schema change**:
`prompt_runs.input_hash` already identifies a batch and is stable — Hartley's
three attempts each produced exactly 277 distinct hashes and the sets are
identical. Per-batch persist costs 0.05–0.1% of the batch that made the LLM call
(8.9–17.9 ms against a measured 18,631 ms median).


**Measured twice, 2026-08-19 and 2026-08-20 — this is now the blocker for one
real source, not a hypothetical.** Hartley (`sources.id=45`, 673 pages, 277
extraction batches) completed **277/277 both times** and then hit a 429 at the
staged compile, and both generations are `discarded` with zero surviving units:

```
GEN-fe8d892e status=discarded created=2026-08-20T12:56:27Z
GEN-c5d4a51c status=discarded created=2026-08-19T11:19:09Z
knowledge_units for source 45: none
```

Roughly 90 minutes of provider work destroyed, twice, at the last step.

Three things make it structural rather than bad luck:

- **The 429 is a burst limit, not exhaustion.** A trivial `agy` call succeeded
  within a minute of the failure. Quota recovers; the run does not.
- **Extraction spends the budget that publish then needs.** By the time the
  staged compile runs, the same window has already absorbed 277 batches.
- **The retry restarts at batch 1**, so it re-spends the whole budget and
  arrives at the same wall. `_raise_capacity_error` sets a 300 s backoff on the
  client instance, but `run_next_job` builds a NEW client per job, so that
  backoff is discarded — a retry that simply waited five minutes would likely
  have published.

So a source of this size cannot currently complete, however many times it is
retried. The cheap half of the fix is not resumability at all: it is honouring
the capacity backoff across the retry. The expensive half is not discarding a
completed extraction because the step after it was rate-limited.


**Settled 2026-08-21: retrying cannot fix this, and the job history proves it.**
v0.61.1 made a rate-limited job wait instead of restarting instantly. It helped
and it was not enough. Every attempt, from the job's own `job_events`:

```
08-19 11:24  attempt 1  reached 277/277  -> 429 at publish
08-19 11:26  attempt 2  reached 0/1      -> 429 immediately   (pre-v0.61.1)
08-19 11:28  attempt 3  reached 0/1      -> 429 immediately
08-20 12:58  attempt 1  reached 277/277  -> 429 at publish
08-20 17:46  attempt 1  reached 277/277  -> 429 at publish
08-20 18:48  attempt 2  reached 183/277  -> 429 mid-extraction  (after a 5-min wait)
```

The backoff works: the waited retry reached **183** where the instant ones
reached **0**. But the window recovers roughly 183 batches' worth in five
minutes and the job needs 277 **plus** the publish that follows — so each
attempt spends the budget from batch 1 and arrives short. More retries and
longer backoffs only change where it dies.

**So the expensive half of this item is not an optimisation, it is the only
path for a source this size.** Preserving a completed extraction across a
failure of the step after it is what makes Hartley ingestable at all; nothing in
the retry dimension can substitute for it.

Note what made this diagnosable: `reached` on the retry event (v0.61.1). Without
it the six rows above would read as six identical failures with a batch counter
at 1, and "the window is shrinking" would have been invisible.

### 6. `.curator` state audit — the remainder

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

### 7. `graph_entities` / `source_spans` transport on a surrogate id

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

### 8. Community hierarchy is flat by construction

`_entities.py` hardcodes `level = 0`; one community holds 176 of 965 entities
while 152 of 233 are single-relation pairs. §27.4 permits the degraded
connected-components fallback but requires it be "surfaced by the audit" —
`config_hash` records it only as an opaque digest and `graph_audit` returns
violations only.

### 9. Backend `agy` spawn has no OS sandbox (opened by v0.56.1)

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

**Related to item 3 (external-file access)** but not the same: this item is
about what the spawned CLI is *permitted* to read; item 2 is about the backend
being unable to *tell* a denial from a missing file. A sandbox here changes
which denials happen; item 3 changes whether we can explain them.

### 10. Retrieval and projection leftovers

- Span segmentation isolates single-word fragments
  (`pipeline/source_spans.py` splits on blank lines with no minimum length).
- One stale CTX file survives re-ingest (bounded — the index carries no CTX
  projection, so it cannot be retrieved).
- Retro-repair for vaults carrying a dead source row from a pre-v0.46.0 move;
  `wiki lint` reports them but nothing fixes them.

### 11. PDF whole-document search — PLANNED, awaiting approval

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

### 12. Drafts not yet planned

- Vault Storage Governance & Quota Visibility —
  `.agents/drafts/vault_storage_governance.md`
- Native PDF Annotation & Asset System —
  `.agents/drafts/pdf_annotation_system.md`
- Web Search Integration — no current plan; re-plan from current provider,
  privacy, and cost constraints.

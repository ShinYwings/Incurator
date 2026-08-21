# RELAY — Active Goal: PDF Reading Assistant (plan 05)

## Active Goal

Make the sidechat and popover actually do the three jobs the user named: help
read PDFs/papers/books, remind them of notes they already wrote, and help them
find new value in both. The v0.53.x line fixed *symptoms* of a prompt stack that
had been built as a scope-limiter; plan 05 rebuilds it around the role.

## Plan Reference

- Master plan: `.agents/plans/05_pdf_reading_assistant.md`
- Arena record: `.agents/plans/pdf_reading_assistant_arena/`
  (`00_problem.md`, `A_prompt_role_audit.md`, `02_critique_redteam.md`)

## Analysis & Reasoning

The prompt audit is the reason this plan exists. Sentences in the stack,
classified by which duty they served:

| duty | enabling | limiting |
|---|---|---|
| 1 read/explain the document | 32 | 13 |
| 2 remind me of my own notes | 6 | 3 |
| 3 find new value | **4** | 0 |

Duty 3's four hits were MCP *tool descriptions* — no sentence anywhere said
that finding new value is the job. Both duty-2 sentences cancelled themselves
mid-clause ("…connect it to the user's existing notes, **but avoid**…"), while
three unhedged prohibitions said answer ONLY about the selection. The model
complied with the prohibitions. That is exactly what the user complained about.

## Progress Status

- [x] **P0 — Prompt re-pose** → v0.54.0 (#153). Three duties stated up front;
      general-knowledge narration mandate deleted; prohibitions rewritten as
      descriptions. Gated by `promptRoleBudget.test.ts` (≤17,000 chars,
      ≤23 negatives, all three duties present).
- [x] **P1 — Contract** → v0.56.0 (#156). PLUGIN_SCHEMA §13.7 carries the
      three-duty role and the provenance-from-results rule.
- [x] **P2 — Per-region pixel routing** → v0.55.0 (#154).
      `read_pdf_page_image` renders any page off-screen and reads the pixels.
- [x] **P3 — Citation resolution (depth 1)** → v0.56.0 (#156). Bibliography
      parse with continuation, `[8]` → paper, resolved pre-turn. Unmatched
      citations DROP (§4.8); `[^8]`, `[text][8]` and code indices are excluded
      by isolating cases, not by a guard that happened to be green.
- [x] **P4 — Provenance surface** → v0.56.0 (#156). Assembled from resolution
      results; no output regex.
- [x] **P5b — Query-time workspace consultation** → v0.57.0 (#158). Notes under
      `01_Workspaces/<project>/` are read when you ask and never ingested.
- [ ] **P5a — Vault coverage.** The remaining ingest half: the `[Source]`
      spaces (`03_Notes/`, `04_Resources/`), NOT `00_System/`. Partly underway —
      see the live-vault state below.
- [ ] **P6 — Live acceptance.** The definition-of-done question, end to end.

Out-of-plan work that shipped alongside: v0.53.3 (#152) narration removal,
v0.54.1 (#155) the backend `ANTIGRAVITY_*` scrub, v0.56.1 (#157) the agy
`read_file(*)` permission, v0.58.0 (#159) long-ingest observability.

## Critical Context / Blockers

**`isScannedLike` cannot route pixel reads, and no threshold changes that.** It
is a whole-page aggregate. Measured on "3D Line Mapping Revisited" p.11 via
pdf.js `getOperatorList()`: 14 image draw ops against 4,193 text chars, versus a
prose control page's 5 ops. The page holding the rasterized equation is
text-dense by every page-level measure. Only the model answering the question
knows the answer is missing — hence a model-invoked tool.

**Naming a tool in the prompt is not the same as making it reachable, and the
reverse can regress a known bug.** v0.55.0 first shipped with three prompt sites
steering *away* from the new tool, then with wording ("a tool for reading a page
as an image") that a CLI-routed model — which receives no local tools at all,
while agy holds a persistent `read_file(*)` grant — could satisfy with its own
file reader, re-opening the v0.48.4 `no output produced` failure. Every site now
names `read_pdf_page_image` literally. **Prompt assembly is still not
provider-aware; that is the open follow-up.**

**`buildRecencyAnchor` is the easiest site to forget.** It is emitted last, at
the recency position, and duplicates the pointer rule. It has now been missed
twice by two different changes. Any edit to the pointer instruction must touch
it too — `blockAnnouncement.test.ts` now asserts every emitted block is named in
both the anchor and the pointer instruction.

**Live vault state (P5a, `second_brain`)** — read from
`.cache/vaults/13ed51f8b06cb88e/state.sqlite`, not `.curator/state.sqlite`,
which is a 0-byte stub:

- 44 sources tracked, all L1 done. L2: 18 done / 18 pending / 8 skipped.
  L3: 18 error. **No L2 job is currently queued for the two pending books** —
  Hartley (`sources.id=45`) and Přibyl (`46`) sit at `l2_status='pending'` with
  nothing in `ingest_jobs`, so they will not advance on their own.
- `vision_page_cache` holds 104 pages of Hartley's 673. The run that produced
  them completed (exit 0, `l1_status='done'`), so those pages are genuinely
  cached and the next run skips them.
- `job_events` is empty and correctly so: rows only exist for jobs that ran
  under v0.58.0 or later. Do not read the empty table as the v0.58.0 fix having
  failed — enqueue a job and check again.

**Vision transcription is verified end to end** as of the Hartley run; the
earlier 429-capacity blocker is cleared.

**Environment**: venvs at the repo root — `.venv` runtime, `.venv-dev` checks.
Never `backend/.venv`, `backend/uv.lock`, or backend-local caches. Plugin tests
need `plugin/src/generated/buildManifest.json`; CI stubs it, so stub it locally
too. Use far-future test sentinels (2099-01-01) — two tests expired mid-session
on a plausible near date. Running `ruff`/`mypy` without `--cache-dir` outside
the repo drops a cache at the repo root and fails `test_workspace_hygiene.py`;
use `scripts/backend-check`.

## Interposed line: v0.59.0 → v0.61.1, all shipped

| release | what it fixed | remainder |
|---|---|---|
| **v0.59.0** (#160) | job progress emitted from the loop that runs; v0.58.0 had wired it to `WorkerCallbacks`, which an L2 job never invokes | L3 has no per-step heartbeat — `run_l3_from_existing_atoms` takes a callbacks factory and never calls it |
| **v0.60.0** (#162) | the CLI is asked for a value, not prose it may compute with `python3` | the schema MUST be flattened; unflattened, agy returns SUCCESS with an empty structure |
| **v0.61.0** (#163) | "denied" is no longer reported as "missing"; `os.access` returns True for a TCC-denied file | the plugin's own read path still surfaces a raw Node error |
| **v0.61.1** (#164) | a rate-limited job stops restarting into the same wall | the completed extraction is still discarded — ROADMAP 5's expensive half |

**The roadmap was re-sorted and renumbered** (2026-08-20). Item numbers in older
notes will not match. Current head: 1 formula recovery, 2 re-derivation,
3 external-file access (shipped), 4 System Integrity, 5 resumable L2.

**ROADMAP 1's Arena closed with no build** — five measurements removed every
premise it would have planned against, including its own "~48 regions" (actually
2,121) and a header that contradicted its blocker list. It filed **item 2**: a
source at `l2_status='done'` is never re-parsed, so a shipped parser fix reaches
only sources ingested after it. Item 1 should not move until item 2 does.

**Hartley (`sources.id=45`) — third attempt running.** It completed 277/277
extraction twice (08-19, 08-20) and lost both at the staged compile to a 429;
both generations are `discarded`. v0.61.1 means a refusal now defers with the
job left queued instead of restarting from batch 1. Worker:
`scratchpad/run_hartley5.py`, log `scratchpad/hartley5.log`.

**Live-run mechanics.** A worktree run creates a NEW EMPTY state DB — the repo
cache resolves from the running code's own location (`config.py:354`). Redirect
`config.get_global_config_dir` to `/Users/shin/shinywings/Incurator/.cache/config`.
The real DB is `.cache/vaults/13ed51f8b06cb88e/state.sqlite`; `.curator/state.sqlite`
is a 0-byte stub.

**Recurring lesson from this line of work.** Four of these releases had a defect
found by *running* the thing rather than by a test: a writer wired to a dead
path, a schema that returned SUCCESS with nothing, a resolver that degraded a
denial into a successful stub ingest, and a block that would have disabled a
healthy failover. Green tests did not catch any of them.

## Interposed: ROADMAP 5 SHIPPED — v0.62.0 merged (PR #166, 2026-08-21)

Plan and evidence ledger deleted on merge per the workflow; read them with
`git show f182efe^:.agents/plans/06_resumable_l2_evidence.md`. Arena record stays
at `.agents/plans/resumable_l2_arena/`.

**Live acceptance: 277 extraction calls → 0, 5,100 s → ~120 s**, counted against
a baseline snapshot (`prompt_runs` 1941 before and after). Testbed E2E through
the CLI: SIGKILL mid-extraction → resume adopts 3 of 5 batches → **published,
90 units, `wiki lint` exit 0**.

**Two lessons worth keeping.**

1. *Shipping half the feature was worthless, and only a live run said so.* The
   first version had per-batch persistence alone; the run finished 277/277 in 85
   minutes and ended with **zero units**, because `compile.py`'s staged-compile
   failure handler DELETED every row it had written. All 19 unit tests passed
   against it — they call `extract_knowledge_units` directly and never reach that
   handler. Fifth release in a row where running it found what tests could not.
2. *I moved the goalposts twice.* Mid-run I called "the extraction survives" the
   release condition, which the plan does not say; then I showed the publication
   clause on the testbed source and presented it as closing the gap on source 45.
   Both were substitutions. Accepting a substitution is the reviewer's call.

**Design facts to not re-derive:**
- Resume keys on `prompt_runs.input_hash` — no schema change. It hashes the
  rendered prompt, so a template edit invalidates every batch by construction.
- Stable only for an UNCHANGED span set. `_spans_block` renders span ids, so an
  L1 re-parse invalidates everything. Measured: 99.7% span overlap still shared
  only 21.7% of batch hashes.
- Never key on batch index (`optimal_chunk_chars` changes the count 12/23/46/93)
  and never on span coverage (1,790 of 8,692 spans appear in >1 batch).
- `validator_status` must accept `repaired`, not only `ok` — 57 such runs in the
  live vault carry 687 units.
- The keep-set goes through a TEMP TABLE, never `id NOT IN (?,?,…)`: SYSTEM_
  BEHAVIOR caps queries at 900 bind parameters and source 45 alone needs 5,358.

**Hartley (`sources.id=45`) is STILL unpublished — ROADMAP 5b, not this work.**
Its staged compile dies in `curator.entity_relation_extract`: agy writes a Python
script and runs it, the command is denied, the whole compile fails. Publishing
needs **every** graph batch to succeed; source 45 needs **~87** and agy's measured
success rate is **57%**, so P(clean run) ≈ **7×10⁻²²**. Retrying cannot work.
Its 5,358 extracted units are parked, unpublished and adoptable, so the retry is
now ~2 minutes rather than 85 — whenever 5b is fixed.

## Immediate Next Action

**P5a** — advance the two pending books. Hartley's L1 and 104 vision pages are
done; what is missing is an L2 job for sources 45 and 46. Then **P6**, the live
acceptance question end to end.

Also open, in rough priority order **against the re-sorted roadmap**:
ROADMAP 2 (external-file access cannot tell "missing" from "not allowed" — the
wall Hartley is behind), ROADMAP 4 (resumable L2 — Hartley finished 277 batches
and lost all of them at publish), ROADMAP 1 (wire formula recovery into the
compile path — built and tested but never invoked), ROADMAP 8 (backend agy
sandbox), and the `wiki add --help` text that still claims L1 runs "without an
LLM call".

---

# ⏸️ Paused Goal (unchanged)

**ROADMAP item 10 — `pdfFullDocumentIndex` consumers.**

The "Background page indexing" toggle writes a value **nothing reads**, so
`search_pdf_anchor` is still limited to already-rendered pages. `fetch_pdf_page`
reads any page the model can *name*, but nothing can *locate* one in an unread
page.

Arena: `.agents/plans/pdf_background_index_arena/`
Plan: `.agents/plans/04_pdf_background_index.md`
Evidence: `.agents/plans/04_pdf_background_index_evidence.md`

Fix the quadratic `upsertPage` first — measured at **26,881 ms** for a 673-page
book against 81 ms for the bulk path (331x). The evidence ledger also records an
unanticipated finding: `search()` alone costs 59.7 ms on a full book index.

ROADMAP item 1 (formula recovery) remains blocked on three prerequisites, with
an Arena record at `.agents/plans/formula_recovery_arena/`.

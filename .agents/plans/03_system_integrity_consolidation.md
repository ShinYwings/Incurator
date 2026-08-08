# v0.42.2 → v0.46.0 System Integrity Consolidation — Master Implementation Plan

Date: 2026-08-04 | Status last verified against the code: 2026-08-08
Status: **PARTIALLY EXECUTED** — approved and in progress, not awaiting approval.

The original line read "AWAITING USER APPROVAL … No code may be written until
they are." That has been false since v0.44.0. Shipped from this milestone:

- **B4** — v0.44.0
- **B3 P1–P4** — v0.45.0

Still open, and the reason this plan stays in the workspace (all P2/P3 now —
the milestone has no P1 left):

- **B2 — COMPLETE (v0.49.2 → v0.50.2).** CAND-03 conflict-archive EXDEV,
  sync_db-3 export-stamp race, sync_db-1 truthful import outcome, sync_db-2
  single-source trigger definitions, sync_db-4 locked device-state RMW.
  **Zero P1 items remain in this milestone.**

  Every one was found by measuring the running code, not by reading this plan.
  The plan named the item; the measurement found what was actually wrong with
  it, and in all five cases that differed from the one-line description. Two
  also introduced faults that only a second pass caught — a lock that
  deadlocked on nested acquisition, and a detector that refreshed on every open
  — so a fix here is not finished until a test has been verified to fail
  without it.
- **B3 P5** synthesis dep-hash freeze · **P6** delete the dead L2
  checkpoint-resume (table migration) · **P7** record a reason on legitimate
  skips (needs a decision: `layer_error` is named for errors, `error_reason`
  already exists).
- **B5 / B7** — each requires its own Arena plan.

Note for B2: the formula-recovery Arena independently found a live cross-device
sync defect in this same area — `source_spans` has no `updated_at`, and
`db_sync.py:87` uses the immutable `created_at` as its LWW clock, so any
`metadata` mutation (which shipped `recover_formula()` already performs) is
silently dropped by a peer on import. Fold that into B2 rather than solving it
twice.

Supersedes on closure: `.agents/plans/01_system_stability_overhaul.md` and
`.agents/plans/02_v032_regression_audit.md` (ROADMAP items 1 and 2).
Arena record: `.agents/plans/system_defect_audit_arena/` — 4 inspector
proposals, 4 domain critiques, 1 main-agent critique, `03_synthesis.md`.

## 1. Objective

Close every debate-confirmed defect from the v0.42.x system audit as a sequence
of independently reviewable releases, and retire the two overlapping roadmap
umbrellas into this one milestone.

**Definition of done:** batches B1–B7 merged (or explicitly re-queued with a
written reason); zero P0/P1 outstanding; every P2 fixed or queued with reason;
Gate G0 (§7) resolved by either running the three missing audit passes or
recording the accepted gap; `01_system_stability_overhaul.md` and
`02_v032_regression_audit.md` deleted; ROADMAP items 1 and 2 replaced by this
milestone.

## 2. Explicit Non-Goals

- **No latency work.** The dominant cost is the provider service handshake
  (8.2–12.2 s per CLI round-trip, flat across model and effort; measured
  2026-08-04, recorded in `USER_REPORT.md`). Incurator cannot shorten it and
  this plan must not re-derive or re-litigate that.
- **No prompt-architecture v2 harness.** Four inspectors produced zero
  prompt-shape defects; building the harness now is speculative infrastructure.
  Iceboxed with a named re-entry trigger (§6).
- **No god-file decomposition program.** No confirmed defect traces to file
  size. Iceboxed with a named trigger (§6).
- **No new features.** ENH-01..05 stay out; ENH-01 becomes a deferred milestone
  that will absorb `compile_pipeline-2(b)`.
- **No mega-batch.** Mixing all 22 items into one release makes any single
  rollback a rollback of everything.

## 3. Strict Quality Conditions & Release Gates

Per batch, without exception (Universal Strict Workflow):

- Docs-first: the spec/guide sentence changes **before** the code; EN guide
  first, then the faithful `_KR.md` mirror.
- Failing test first, and it must assert **behavior**, not source text, wherever
  the behavior is reachable in a test harness.
- `scripts/backend-check pytest | ruff | mypy` and
  `npx vitest run -c ./plugin/vitest.config.ts` all green.
- Isolated testbed + Reference Mode smoke for any batch touching ingest, sync,
  or retrieval. Never the production vault.
- Version consistency across `pyproject.toml`, `package.json`, `manifest.json`,
  `package-lock.json` (both version fields); spec titles bumped only on a
  `MAJOR.MINOR` change.
- PR with latest-head CI green before merge.

Batch-specific hard conditions:

- **B2**: an import that drops a row must never report it as `inserted`; a bad
  peer file must not wedge subsequent passes; two-replica convergence test.
- **B3**: one primitive fix, asserted by a test that runs `recover_stale_jobs`
  **between** the simulated crash and the retry, proving the generation id is
  unchanged and the LLM client is never called.
- **B5**: exactly one pack `contract_version` bump for the whole surface.
- **B7**: migration rehearsed on a disposable copy first; rollback drill;
  identical schema fingerprint on re-run.

## 4. Locked Design Decisions (Arena Consensus)

1. **`sources.layer_error` is overloaded as both human error text and pipeline
   control flow.** B3 is organized around fixing that *primitive* (an `UNSET`
   sentinel for status writers, a marker-preserving recovery predicate, an
   error-only writer), not around its three symptoms (CP-1, CP-3b, CP-4).
2. **`INSERT OR REPLACE` is rejected** as the sync fix — it trades a silent drop
   for a silent overwrite. The import must detect the collision and take the
   documented LWW path, reporting a truthful outcome.
3. **CP-2 splits.** The dep-hash freeze (~3 lines, where the permanent damage
   lives, repairs already-frozen vaults) ships in B3; the atomicity half defers
   into ENH-01, which rewrites the same path anyway.
4. **RC-4 and CAND-04 ship together** in B5 — they edit the same functions and
   each alone would force a pack `contract_version` bump.
5. **CAND-03 (`Path.rename` EXDEV) ships with B2**, because it is the specific
   instance of B2's general disease: a per-file error that wedges every retry.
6. **Deleting CP-4's promotion beats recomputing grounding sets in
   `_mark_clean_sync_status`** — the latter duplicates compile-time policy into
   the sync command and creates a second place for §4.1 to drift.
7. **B2 makes the P1 *reported and non-wedging*; B7 makes replicas *converge*.**
   These are different claims and the plan never conflates them.

## 5. Scope Exclusions & Stop Conditions

**Exclusions:** ENH-01..05; prompt-v2 harness; decomposition program; latency
work; the two never-run audit domains (see Gate G0).

**Stop conditions — halt and return to the user:**

- Any batch requires a schema migration not already scoped to B7.
- B7's id remap cannot be proven to cover every referencing column.
- The B7 migration rehearsal fails, or the rollback drill does not reproduce an
  identical schema fingerprint.
- A batch's fix requires amending a spec sentence that was not already flagged
  as a contract decision in §8.
- The same validation gate fails three times without a new diagnosis
  (`rollback_strategist`).

## 6. Roadmap Merge

ROADMAP items 1 and 2 are replaced by this single milestone.

| Old workstream | Disposition |
|---|---|
| Release-chain integrity (P6–P10) | Closes through B1 + B2; per-batch gates carry B3–B7 |
| Prompt architecture v2 | **Icebox.** Trigger: first USER_REPORT item where a provider returns a structurally wrong payload a fixture would have caught |
| Broad-exception hardening (§32) | B4 fixes the three known instances; the **class** stays open behind Gate G0 |
| Safe god-file decomposition | **Icebox.** Trigger: a third new defect in the same file region after B1/B3 land |
| Measured performance | **Closed.** Sole descendant is ENH-01 (cost, not latency) |
| Existing-surface UX | **Dissolved.** Two concrete items map to B3/B6; the rest re-enters via USER_REPORT |

## 7. Evidence Ledger

- **Repository reality:** master `623a755` (v0.42.1). All gates green at plan
  time: backend pytest 1414 passed / 6 skipped / 4 xfailed; Ruff clean; mypy
  clean (127 files); plugin Vitest 873 passed / 80 files; production build clean.
- **Rollback anchor:** `623a755`. Each batch additionally anchors on its own
  pre-merge master.
- **Dirty worktree:** none at plan time; the arena branch
  `chore/system-defect-audit-arena` holds only `.agents/` documents.
- **Audit coverage boundary (NOT a complete audit):** 4 of 6 planned domains
  ran. `exception_hygiene` and `docs_parity` never ran (their inspectors died on
  provider limits across three attempts). Four `plugin_lifecycle` Pass-A
  findings (F1–F4) were never adjudicated. **Gate G0** below.
- **Debate outcome:** 19 findings survived; 15 confirmed, 4 downgraded, 0
  refuted. Plus 6 CAND items from the earlier single-agent pass = 22 work items
  after dedup.
- **Severity note:** `sync_db-1` was rated **P0** by the main-agent critic
  (silent cross-device row loss) and **P1** by the synthesis (data survives on
  the origin replica; this is divergence, not destruction). The plan proceeds at
  P1 but the disagreement is recorded rather than resolved silently.
- **Migration risk:** only B7 bears a migration. It must be rehearsed on a
  disposable copy before touching any real DB.
- **Do not touch:** the consumed D2 holdout (never rerun), the active testbed
  (an unrelated historical fixture), and the production `second_brain` vault.

### Gate G0 — CLOSED 2026-08-05

All three passes ran (Q8 = Option A). The audit is no longer partial.

**Plugin Pass-A adjudication** (`04_g0_plugin_pass_a.md`):
F1 **CONFIRMED and worse than filed** — and independently re-verified by the
main agent against all three call sites. Shipped as **v0.42.3 / PR #114**:
Quick Query called `fetchActivePdfPage` without an expected document id
(`quickQueryPopover.ts:491`) while the local tool runner opts in
(`main.ts:1860`), and the guard is opt-in
(`if (expectedDocumentId !== undefined && …)`). A tab switch during the
multi-round resolution read pages from the wrong PDF — and because the resolver
writes fetched pages back under the `searchDocumentId` it was handed, foreign
text contaminated the original document's BM25 index for later queries too.
F2 CONFIRMED (P2), F3 CONFIRMED (P3), F4 DOWNGRADED (unreachable branch).

**Exception hygiene** (`04_g0_exception_hygiene.md` + critique):
4 filed, 2 confirmed, 2 downgraded — the class is smaller than feared.
- `eh-1` [P2] CONFIRMED → **B4**. `add_atom_from_insight`
  (`ingest_llm.py:685-690`) collapses every failure to `return None` with no
  logging, and the caller only prints on success — so `wiki query --update`
  skips the atom creation the flag promises, invisibly. No test covers it.
- `eh-3` [P3] CONFIRMED → **B4**. `secret_store.get_secret` swallows
  `InvalidToken` and returns `""`, so a secret that cannot be decrypted on this
  machine (reachable via this project's own cross-device config sync) is
  reported to the user as a missing API key.
- `eh-2` → P3. Real (corrupt dismissal store silently resets to `[]`, then the
  next dismissal rewrites it), but the critic correctly notes it welds together
  two defects; **file the non-atomic `_save` separately** as a durability item,
  not in the §32 batch.
- `eh-4` → P4 nit. §32 explicitly permits a broad catch at a cleanup boundary;
  only the logging is missing and the downstream symptom is already surfaced.

**Docs parity** (`04_g0_docs_parity.md`): produced; findings not yet folded in.

Consequence for the workstream disposition: B4 may now honestly be described as
closing the §32 class, because the sweep it was waiting on has run.

### Gate G0 — original definition (kept for the record)

Either (A, recommended) run three read-only passes — adjudicate plugin Pass-A
F1–F4 starting with **F1 [P1]** (Quick Query `fetchActivePdfPage` called without
`expectedDocumentId` at `quickQueryPopover.ts:484-492` while the local-tool call
site does pass it at `main.ts:1859-1860`, alleged wrong-PDF page splicing), the
repo-wide §32 sweep, and the docs-parity sweep — folding survivors into B1/B4
before those ship; or (B) the user accepts the gap and the closure note records
that domains 5–6 were never audited and F1–F4 never adjudicated.

**F1 should be adjudicated first regardless.** If it holds it is a
wrong-knowledge defect, which would make B1 the highest-value batch rather than
the safest one.

## 7a. User Decisions — ANSWERED 2026-08-04

- **Q8 Gate G0 → run all three passes.** Adjudicate plugin Pass-A F1–F4, run the
  repo-wide §32 `exception_hygiene` sweep, and run the `docs_parity` sweep
  before the batches they would feed (B1/B4) ship.
- **Q12 P1 ordering → no carve-out.** Ship B1 then B2 as planned.
- **Q3 CAND-04 → implement the spec.** Real file-level locator resolution
  (existence, heading/anchor scan, content-hash drift, duplicate-anchor
  detection, `block_id`). §29.3/§29.4 and SEARCH_ENGINE §12.2 stand as written;
  the code rises to meet them. Accept the added file I/O on the evidence path.
- **Q7 CAND-06 → REFRAMED BY THE USER; the original finding was wrong.**
  Sidechat is not supposed to bind a `curate.yml` workspace at all. The real
  defect is that ONE parameter carries TWO meanings:

  ```python
  # every other hidden plugin command (12 sites, commands/plugin.py)
  workspace_path: ... help="Vault root override."

  # plugin_context_fetch ONLY (commands/plugin.py:513)
  workspace_path: ... help="Workspace/vault path."
      _plugin_paths(workspace_path),   # → _resolve_root_or_die(): VAULT ROOT
      workspace_path=workspace_path,   # → resolve_curate_policy(): KRS WORKSPACE
  ```

  The plugin correctly sends the vault root; the backend then *also* interprets
  that same value as a KRS workspace selector. So "the curation lens is inert
  for chat" is the intended shape, not a defect — but a vault-root `curate.yml`
  silently becoming the policy for every chat turn is real. The user notes this
  misnaming has caused a problem before.

  **B6 is rescoped:** de-overload the parameter (separate vault-root resolution
  from KRS workspace selection across the hidden plugin API and MCP surface, and
  make the plugin pass only the vault root) instead of teaching sidechat to walk
  ancestors for a `curate.yml`. The rejected approach would have changed which
  knowledge chat sees — explicitly not wanted.

Still open, non-blocking with accepted defaults: Q9, Q10, Q11, Q14.
Still open and blocking their own batches: Q1, Q2, Q4, Q5, Q6, Q13.

## 8. Blocking Decisions (must be answered before any coding)

Full text and defaults: `system_defect_audit_arena/03_synthesis.md` §7.

| Q | Decision | Blocks |
|---|---|---|
| Q1 | `l4_status` on report/synthesis failure: change code to `'error'`, or amend §4.1 to bless `l3='error' + l4='skipped'`? **Code-change flips B3 patch → minor.** | B3 |
| Q2 | L2 checkpoint-resume dead code: delete, or complete all three preconditions? | B3 |
| Q3 | CAND-04 locator: implement real file-level resolution, or amend §29.3/§29.4 + SEARCH_ENGINE §12.2 to a DB-metadata contract? | B5 |
| Q4 | Is `sync_key` an immutable birth identity, or a derived mirror of `relpath`? | B7 |
| Q5 | Rewrite existing bad `sync_key` values by migration, or leave historical splits? | B2 |
| Q6 | (a) snapshot hard-vs-soft conflict tiering; (b) is cross-process Windows sync supported? (`durable_io.locked_path` degrades to a thread lock there) | B5 / B2 |
| Q7 | CAND-06: which workspace binds a chat turn, and what does a vault-root `curate.yml` mean? | B6 |
| Q8 | Gate G0: run the three missing passes, or accept the gap? | closure |
| Q12 | Carve out a `hotfix/v0.42.2-sync-import-truthfulness` for the P1 ahead of B1? | ordering |
| Q13 | Is defining "stale" inside an existing §2.1.3 sentence a clarification (B1 stays patch) or a contract change? | B1 numbering |

Non-blocking (defaults acceptable): Q9 (status UX note), Q10 (when to delete
the old plans), Q11 (§13.1 mutable tie-break), Q14 (icebox both workstreams).

## 9. Execution Phases

Each batch is a full Universal Strict Workflow cycle. B5 and B7 additionally
require their own Arena plan before implementation.

- **P0 — Decisions & Gate G0.** Collect §8 answers in one pass; run the G0
  passes if Q8 = A. No code. → verify: every blocking Q answered; G0 survivors
  folded into B1/B4.
- **P1 — B1 `v0.42.2` (patch): plugin lifetime & teardown.** PL-1 (`return await`
  so `finally` runs on settle, both call sites), PL-3 (age-guarded per-subdir
  `chat_images` sweep), PL-2 (detach reposition listeners against the attach-time
  window), PL-4 (`SyncScheduler.dispose()` disarms `pending`). → verify: plugin
  Vitest + tsc + build; behavior-level abort test.
- **P2 — B2 `v0.43.0` (minor): cross-device sync integrity.** sync_db-1 Half A
  (truthful import outcome + `conflicted` reporting + continue-past-bad-peer +
  checkpoints), sync_db-2 (`sources_set_sync_key` no-op trigger), sync_db-3
  (`last_export_ts` stamped after the snapshot read), sync_db-4 (locked
  device-state RMW), CAND-03 (`shutil.move`). → verify: two-replica convergence
  test; a dropped row is never counted as inserted; testbed sync smoke.
- **P3 — B3 `v0.43.1` (patch, minor if Q1 = code): compile-status truthfulness.**
  The `layer_error` de-overload primitive fixing CP-1 / CP-3b / CP-4, plus the
  CP-2(a) freeze fix and the CP-5 resolution from Q2. → verify: recovery-between-
  crash-and-retry test; no LLM call; generation id stable.
- **P4 — B4 `v0.43.2` (patch): observable degradation & budget.** RC-2 (expansion
  reserve double-subtraction), CAND-01, CAND-02, RC-5(a), CAND-05 docs rider.
  → verify: an advertised `next` handle is actually admissible at the same
  `limit_tokens`; every swallowed path logs or warns.
- **P5 — B5 `v0.44.0` (minor): context pack contract v2.** RC-3 → RC-1 → RC-4 +
  CAND-04, RC-5(b). **Own Arena plan required.** → verify: one contract bump;
  snapshot conflict is real, not tautological; no fabricated clickable locator.
- **P6 — B6 `v0.45.0` (minor): workspace curation binding.** CAND-06 per Q7.
  Depends on B5's `policy` block as the observable. → verify: an in-workspace
  note binds its KRS; the applied filter set is visible.
- **P7 — B7 `v0.46.0` (minor, migration): sync identity merge & convergence.**
  sync_db-1 Half B (per-index merge + id remap) and sync_db-5 per Q11. **Own
  Arena plan required.** → verify: migration rehearsal on a copy, rollback
  drill, identical schema fingerprint, replica convergence.
- **P8 — Closure.** Delete `01_system_stability_overhaul.md`,
  `02_v032_regression_audit.md`, and this plan; reset RELAY per the documented
  IDLE procedure.

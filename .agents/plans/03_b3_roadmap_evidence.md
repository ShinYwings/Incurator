# B3 Evidence Ledger — Compile-Status Truthfulness

Created: 2026-08-06, immediately before coding starts (PLAN_TEMPLATE mandate).
Master plan: `.agents/plans/03_system_integrity_consolidation.md` (batch B3).
Branch: `fix/b3-compile-status-truthfulness`.

## Rollback Anchor

- Base: `master` at the merge of PR #120 (`v0.44.1`).
- Every phase below must pass `scripts/backend-check pytest` + `ruff` before the
  next begins. If three consecutive phase attempts fail, `rollback_strategist`
  applies: revert the branch to this anchor and return to planning.

## Locked User Decisions

- **Q1 = `error`.** On a synthesis failure the affected sources get
  `l4_status='error'`, not `'skipped'`. This is a code change, which promotes B3
  from Patch to **Minor → v0.45.0** and requires the four spec titles to move to
  the v0.45 line.
- **Q2 = delete.** The L2 checkpoint-resume path is removed outright, not
  completed.

## Current Reality, Measured (not assumed)

Measured against the real 36-source vault (`13ed51f8b06cb88e/state.sqlite`,
read-only) after the post-v0.43.0 build.

### The `skipped` statuses carry no diagnosis at all

10 of 36 sources sit at `l2_status = l3_status = l4_status = 'skipped'` while
`status = 'curated'`. **Every one has an empty `layer_error` AND an empty
`error_reason`.** Nothing in the record says why.

Two of them contradict their own status outright:

| source | spans | knowledge_units | l2_status |
|---|---|---|---|
| 28 `03_Notes/…/Pfaffian System.md` | 9 | **11** | skipped |
| 31 `04_Resources/…/Multiple_View_Geometry…EN.md` | 1 | **11** | skipped |
| 17 | 8 | 1 | skipped |
| 30, 33 | 1, 1 | 2, 2 | skipped |
| 19, 21, 22, 23, 24 | 6–7 | 0 | skipped |

A layer that produced 11 units is not "skipped". Either the status is wrong or
the units are stale from an earlier generation — and today nothing in the record
lets a user distinguish those two very different situations. This is the
user-visible face of CP-1/CP-3b/CP-4 and it is the acceptance target for B3: a
terminal status must be accompanied by a reason a human can act on.

### `layer_error` is a three-way overloaded column

It simultaneously carries:

1. **Human error text** — `str(e)` from `ingest_raw.py:1437`, `compile.py:324`.
2. **Pipeline control flow** — the post-publish projection marker.
   `compile.py:67-68` defines `_POST_PUBLISH_PROJECTION_ERROR =
   "post-publish projection failed:"` and `_POST_PUBLISH_PROJECTION_PENDING =
   "post-publish projection pending"`, and `compile.py:296-307` *reads
   `layer_error`* to decide whether to take the `_recover_published_source`
   path instead of recompiling.
3. **Sync annotations** — `"sync_logical_gap:<node ids>"` written by
   `common.py:706,716`.

Any writer that clears the column destroys meaning (2) and (3).

### The status writer clobbers unconditionally

`db/sources.py:507-527`:

```python
def set_source_layer_status(db_path, source_id, layer, status, *, error: str | None = None):
    conn.execute(
        f"UPDATE sources SET {column} = ?, layer_error = ? WHERE id = ?",
        (status, error, source_id),
    )
```

`error` defaults to `None`, so **a status-only write always NULLs
`layer_error`**. There are 35 call sites across `ingest_worker.py`,
`ingest_raw.py`, `ingest_llm.py`, `pipeline/compile.py`, `plugin_api/sources.py`,
`mcp/server.py`, `commands/core.py`, and `commands/common.py`; the majority pass
no `error` and therefore clobber.

`db/jobs.py:154-159` clobbers a second way, explicitly:

```sql
UPDATE sources SET l2_status = 'pending', layer_error = NULL
WHERE l2_status = 'running' AND id IN (…)
```

### CP-4 confirmed: `wiki sync` promotes L3/L4 from a filesystem glob

`commands/common.py:717-731`:

```python
if l2_done and paths.concepts.exists() and any(paths.concepts.glob(f"{PREFIX_L3}-*.md")):
    db.set_sources_layer_status(paths.state_db, l2_done, "l3", "done")
if l3_done and paths.synthesis.exists() and any(paths.synthesis.glob(f"{PREFIX_L4}-*.md")):
    db.set_sources_layer_status(paths.state_db, l3_done, "l4", "done")
```

The existence of *any* `CON-*.md` file anywhere promotes *every* `l2_status='done'`
source to `l3_status='done'`. The promotion is not per-source and consults no
record of what that source actually contributed. On the audited vault 26 sources
report `l3_status='done'`, and there is no way to tell which of those were
computed by `compile_global_l3` and which were promoted by this glob — which is
exactly the defect.

Note the function's own docstring says "Clear stale layer errors once sync has
verified the current graph". Clearing errors is the stated intent; the
`skipped→done` promotion is not, and per Arena decision 6 it is deleted rather
than reimplemented.

## Design Decision Taken Here (deviation from the critique, recorded)

The red-team critique proposed flipping `set_source_layer_status`'s default to an
`UNSET` sentinel so status-only writes preserve `layer_error`. **This ledger
narrows that**, for a reason the critique did not weigh:

Roughly 25 of the 35 call sites pass no `error`, and a blanket default flip
changes all of them at once. Several are *success* transitions
(`compile.py:499` `l2 done`, `common.py:729-731`, `_mark_clean_sync_status`)
where clearing a now-stale error is the correct and intended behavior — the
docstring at `common.py:717` says so explicitly. Flipping the default silently
converts those into "keep the stale error forever", trading the current bug for
its mirror image and touching 25 sites to fix a marker destroyed at two.

So: the sentinel is added and the signature gains it, but **the default stays
`None` (clear)**, and `UNSET` is passed explicitly at the sites that must
preserve. Each preserving site gets a comment naming what it is protecting.
This satisfies CLAUDE.md rule 3 (touch only what you must) and keeps every
behavior change traceable to a deliberate line.

If a later batch shows the clobber recurring at new call sites, the default flip
becomes the right answer — but that is a decision to take on evidence of
recurrence, not pre-emptively.

## Phases

Each phase ends with `scripts/backend-check pytest` + `ruff` green.

- **P1 — the primitive.** Add the `UNSET` sentinel to
  `set_source_layer_status` / `set_sources_layer_status`; add an
  `error`-only writer. Fix `recover_stale_jobs` to preserve the projection
  marker via `CASE WHEN layer_error LIKE 'post-publish projection%'` (the
  `LIKE`, not `=`, so both the `_PENDING` and the `_ERROR`-prefixed form
  survive), keeping the `l2_status='pending'` reset that §4.1 L237-239 requires.
  → verify: `recover_stale_jobs` runs **between** the simulated crash and the
  retry, the generation id is unchanged, and the LLM client is never called
  (the batch's hard condition).
- **P2 — CP-1/CP-3b clobber sites.** Pass `UNSET` at the compile-path status
  writes that can run while a marker is live; stop `compile_global_l3` from
  overwriting the real L3 error message with the L4 one (compose
  `f"l3: {…}"` / `f"l4: {…}"` instead).
- **P3 — CP-3a (Q1).** `l4_status='error'` on synthesis failure;
  `test_compile_pipeline.py:409` renamed and inverted; §4.1 updated to spell out
  `error` as a legal `l3_status`/`l4_status` in the global-failure case.
- **P4 — CP-4.** `_mark_clean_sync_status` clears `layer_error` only; the
  `skipped→done` glob promotion is deleted (Arena decision 6).
- **P5 — CP-2(a).** The synthesis dep-hash freeze: a `synthesis_manifest` row
  written *after* the loop as the commit marker, short-circuiting on that row
  rather than the per-node column, and forcing `reemit_synthesis` on unfreeze so
  a truncated DB cannot leave the old full `SYN-*.md` on disk (critique Attack 4).
- **P6 — CP-5 (Q2).** Delete the `if resume:` branch, the `resume` parameter,
  `has_l2_checkpoints` / `insert_l2_checkpoint` / `get_l2_checkpoint_hashes`,
  the `l2_checkpoints` table (migration), and the four tests at
  `test_knowledge_unit_extraction.py:293-400`.
- **P7 — skip-reason truthfulness.** Every terminal `skipped` records why, so
  the ten sources above stop being silent. Uses the P1 error-only writer.
- **P8 — release.** v0.45.0 across the four manifests, the four spec titles to
  the v0.45 line, CHANGELOG, guides + `_KR` counterparts.

## Pre-Validation Baseline (to compare against after)

- Backend pytest: **1427 passed / 6 skipped / 4 xfailed** at v0.44.1.
- Ruff clean; mypy clean (127 source files).
- Plugin Vitest 886/886 across 83 files; `tsc --noEmit` clean.
- Real vault: 10 sources `skipped` with zero recorded reason; 26 `done` with no
  way to distinguish computed-L3 from glob-promoted-L3.

## Scope Cut Taken (recorded, not silent)

This branch ships **P1–P4**: the `layer_error` primitive and its three symptoms
(CP-1, CP-3a, CP-3b, CP-4). That is the coherent unit the Arena identified —
"three findings, one primitive" — and it is what makes the terminal statuses
truthful.

**P5–P7 are deliberately NOT in this PR** and remain open:

- **P5 (CP-2a, the synthesis dep-hash freeze).** Independent of the primitive;
  it is about a partial L4 rebuild being frozen by a per-node hash short-circuit.
  Needs the `synthesis_manifest` commit-marker design plus the forced
  `reemit_synthesis` on unfreeze (critique Attack 4), which is its own change.
- **P6 (CP-5, delete the L2 checkpoint-resume).** A table migration and the
  removal of four tests. Unrelated to status truthfulness; batching it here
  would mean one PR that both changes semantics and drops a schema object.
- **P7 (record a reason on every terminal `skipped`).** This one I added to the
  ledger myself, and on implementation it turned out to need a decision this
  batch should not improvise: `layer_error` is named for errors, while a skip
  reason ("no community report cites this source") is informational, and
  `sources.error_reason` already exists as a separate column. Which column
  carries a non-error reason is a schema-semantics question for the user, so it
  is filed rather than guessed at.

P4 partially delivers what P7 was for: a `skipped` status can no longer be a
disguised failure, because failures are now `error` with a recorded cause. What
remains open is annotating a *legitimate* skip with why it was legitimate.

## Post-Validation Results

- Ruff clean; mypy clean (127 source files).
- `test_compile_pipeline.py` 11 passed, including the inverted
  `test_synthesis_failure_marks_l4_error_and_leaves_l3_done` and the new
  `test_l3_failure_message_survives_the_l4_status_write`.
- `test_plan_b2_staging.py` 16 passed, including the batch's hard condition —
  `recover_stale_jobs` interposed between crash and retry, generation id
  unchanged, LLM client never called — **verified failing before the fix**.
- Spec/version sync 10/10 at v0.45.0 with all four spec titles on the v0.45 line.
- Full backend suite: see the PR body.

### D2 frozen holdout — tripwire fired and was RE-ARMED, not rerun

The P1 edits touch `db/jobs.py` and `db/sources.py`, both of which are in D2's
`evaluated_code.file_sha256` fingerprint set, so the drift tripwire failed as
designed. The holdout is consumed (`run_count: 3`) and must never be rerun; the
documented path is a written non-impact proof plus a hash re-arm.

The proof here is mechanical rather than argued. `failure_atlas_holdout.py` is
unchanged and still hashes OK, and it uses exactly three `db` symbols —
`connect`, `init_db`, `upsert_search_document` — all defined in `db/schema.py`
and `db/_entities.py`, **both of which still hash OK**, and none defined in
either changed file. The harness contains zero references to
`recover_stale_jobs`, `set_source_layer_status`, `ingest_jobs`, or
`layer_error`, so no changed path is reachable from it. `db/sources.py`'s
additions are three new symbols plus a branch taken only on `error=UNSET`; with
`error=None` or a string the SQL is byte-identical. `db/jobs.py`'s change is
confined to one UPDATE statement inside `recover_stale_jobs`.

Recorded as `v0450_layer_error_primitive_rearm` in `D2_HOLDOUT_RESULT.yml`. The
diff on that file deletes exactly two lines — the two stale hashes — and adds
the re-arm block. No metric, `run_count`, `valid_run_count`, or frozen input was
touched.

# Synthesis: Consolidated Defect Inventory, Release Batches, and Roadmap Merge

Date: 2026-08-04 | Agent Persona: `system_synthesizer` (arena closer)
Inputs: `00_problem.md`, `01_proposal_{compile_pipeline,sync_db,retrieval_context,plugin_lifecycle}.md`,
`02_critique_{compile_pipeline,sync_db,retrieval_context,plugin_lifecycle,main_agent}.md`,
`.agents/plans/01_system_stability_overhaul.md`, `.agents/plans/02_v032_regression_audit.md` (P9/P10),
`.agents/ROADMAP.md`, `.agents/USER_REPORT.md` (2026-08-04 CAND-01..06, ENH-01..05).
Status: **Proposal for user approval.** No code, test, doc, or config was modified;
this file is this agent's only write.

---

## 0. Coverage Boundary (read this before trusting the inventory)

The arena did **not** complete as designed, and the synthesis must not imply it did.

| Domain | Inspector ran? | Critic ran? | Findings entering the plan |
|---|---|---|---|
| 1 `compile_pipeline` | yes | yes (`02_critique_compile_pipeline.md`) | CP-1..CP-5 (5, all confirmed; CP-5 downgraded to P3) |
| 2 `sync_db` | yes | yes (`02_critique_sync_db.md`) | sync_db-1..5 (5; -1 confirmed **P1**, -4/-5 downgraded to P3) |
| 3 `retrieval_context` | yes | yes (`02_critique_retrieval_context.md`) | RC-1..RC-5 (5; RC-1 downgraded P1→P2) |
| 4 `plugin_lifecycle` | **twice** (Pass A `F1–F4`, Pass B `PL-1..PL-4`) | **Pass B only** | PL-1..PL-4 (4). **F1–F4 never adjudicated.** |
| 5 `exception_hygiene` | **never ran** | — | none |
| 6 `docs_parity` | **never ran** | — | none |

Two consequences the user must decide on before P10 can be declared closed:

1. **`plugin_lifecycle` Pass A F1–F4 are undebated.** The critic states its remit
   explicitly: *"Pass A's F1–F4 were not in my remit and are not adjudicated here."*
   F1 is a **P1 claim** — `quickQueryPopover.ts:484-492` calls
   `this.plugin.fetchActivePdfPage(pageNum)` with no `expectedDocumentId`, while the
   guard in `main.ts:1772-1786` is opt-in and the local tool runner
   (`main.ts:1859-1860`) *does* opt in. If true, a tab switch during the backend
   round-trip splices pages from the wrong PDF into a Quick Query answer — that is
   *serving wrong knowledge*, the P0/P1 band of the rubric, and it is the single
   highest-severity unverified claim of the entire run. F2 (`syncAgyMcpConfig`
   silently overwriting a malformed `~/.gemini/settings.json`, non-atomically, while
   its sibling in the same call refuses to), F3 (non-streaming CLI path leaks the
   per-run chat-image dir when pre-spawn setup throws — §2.1.3 "Cleanup robustness"
   implemented on the streaming path only) and F4 (the documented "macOS without
   `sandbox-exec`" degradation branch is unreachable because the path is never
   probed) are likewise unadjudicated.
2. **Domains 5 and 6 produced nothing.** The repo-wide §32 exception sweep and the
   docs-parity sweep never happened. CAND-01, CAND-02, CAND-05 are therefore the
   *only* coverage of those two domains, and they came from the earlier P9 pass, not
   from this arena. Any claim that "the §32 hardening workstream is closed" after
   Batch 4 would be false — Batch 4 closes the *known* instances, not the class.

This document plans the 19 adjudicated items and the 6 CAND items. It treats F1–F4
and the two missing domains as a named, scheduled gap (§6, Gate G0), not as absence
of defects.

---

## 1. Consolidated Defect Inventory (deduplicated)

19 debate-surviving findings + 6 CAND items = 25 raw entries. After deduplication
and splitting along fix boundaries, **22 work items** remain. Nothing was dropped;
where a new finding *supersedes* or *deepens* a CAND item, the relationship is
stated rather than the CAND item being silently absorbed.

### 1.1 Master table

| # | Item | Sev | Area / file | Relationship to CAND / other findings | Contract decision needed? | Batch |
|---|---|---|---|---|---|---|
| 1 | `plugin_lifecycle-1` — `return this.completeViaCli(...)` inside `try/finally` runs `endRequest` at launch, detaching the owner abort listener | P2 | `plugin/src/agent/llm/LLMClient.ts:1250`, `:1318` | independent | no | B1 |
| 2 | `plugin_lifecycle-3` — repo-scoped `chat_images` startup sweep deletes another vault's in-flight payload | P2 | `LLMClient.ts:2325-2331`, `:2295-2299` | independent | **yes (minor)** — §2.1.3 leaves "stale" undefined; the fix must *define* it | B1 |
| 3 | `plugin_lifecycle-2` — reposition listeners detached against the current `activeDoc`, leaking capture-phase listeners on other windows | P3 | `quickQueryPopover.ts:144-146, 191-194, 284-289` | independent | no (any spec hook would have to be *added*, never cited as pre-existing) | B1 |
| 4 | `plugin_lifecycle-4` — `SyncScheduler.dispose()` leaves `pending` armed; a pass runs after unload | P3 | `plugin/src/agent/syncScheduler.ts:64-69` | independent | no | B1 |
| 5 | `sync_db-1` **Half A** — `INSERT OR IGNORE` + unchecked rowcount reports a dropped row as `inserted`; the `sources` sub-case wedges the whole peer chain forever | **P1** | `db_sync.py:1351-1360, 1416-1420, 1293-1301, 1597-1602` | independent; the most serious finding of the run | **yes** — new import outcome (`conflicted`) + report field = §13.1/§32 text | B2 |
| 6 | `sync_db-2` — `sources_set_sync_key` in `SCHEMA_SQL` is a no-op (Python escape ate the backslash); `_triggers_need_refresh` cannot detect it | P2 | `db/schema.py:721` vs `:803`, `:862-868`, `:902-904` | independent | **yes** — SCHEMA §11.17 must state whether existing bad `sync_key` values are rewritten | B2 |
| 7 | `sync_db-3` — `last_export_ts` stamped *after* the snapshot is read; rows committed during export are stranded behind a closed gate | P2 | `db_sync.py:1485-1491`, gate `:1671-1672` | shares the autosync-pass lock with #8 | no | B2 |
| 8 | `sync_db-4` — device sync state is an unlocked cross-process read-modify-write; split device identity mints a phantom peer | P3 | `db_sync.py:656-666, 669-677, 1584, 1607-1608` | fixing it under one `autosync`-granularity lock also closes #7's overlapping-export half | **yes** — Windows `durable_io.locked_path` degrades to a thread lock (`durable_io.py:23`) | B2 |
| 9 | **CAND-03** — `_archive_conflict` uses `Path.rename`; EXDEV across filesystems wedges autosync forever | P2 | `db_sync.py::_archive_conflict` | **same failure class as #5's `sources` sub-case**: a per-file error that permanently wedges every retry. The "continue past a bad peer, report it, keep checkpoints" work in #5 Half A is the general cure; `shutil.move` is the specific one. Ship together. | no | B2 |
| 10 | `compile_pipeline-1` — `recover_stale_jobs` NULLs `layer_error`, destroying the §26.3 post-publish projection marker → redundant LLM recompile + new generation | P2 | `db/jobs.py:154-161`, `compile.py:295-312, 451-454` | one of three symptoms of *the same primitive*: `sources.layer_error` is overloaded as control flow and every status writer clobbers it | no (the `CASE WHEN` + `UNSET` sentinel fix needs no migration) | B3 |
| 11 | `compile_pipeline-3(b)` — the `l4` status write clobbers the real L3 error with the constant "L3 prerequisite failed; synthesis not attempted", which is factually false when only synthesis failed | P2 | `compile.py:1105-1132`, `db/sources.py:523-527` | same primitive as #10 | no | B3 |
| 12 | `compile_pipeline-3(a)` — `l4_status='skipped'` where §4.1 requires `'error'`; an existing green test pins the current behavior | P2 | `compile.py:1124`, `test_compile_pipeline.py:409-441` | spec-vs-test standoff, not a code bug per se | **yes — blocking** (Q1) | B3 |
| 13 | `compile_pipeline-4` — `wiki sync` promotes `l3/l4_status` to `done` from a filesystem glob, overwriting the correctly computed per-source `skipped` | P2 | `commands/common.py:728-731` | same primitive as #10 (the same call blanks `layer_error`); §26.3 "never promoted to authority merely because a file was written" | no, but it has a **UX consequence** (Q9) | B3 |
| 14 | `compile_pipeline-2(a)` — dep-hash short-circuit freezes a truncated L4 layer permanently | P2 | `synthesis.py:113-122` | the durable half of CP-2; independent of the atomicity half | no | B3 |
| 15 | `compile_pipeline-2(b)` — the L4 rebuild is N+1 independent transactions (§27.8 atomic publish violated) | P2 | `synthesis.py:145-172`, `db/_entities.py:2967-2973, 3033-3036` | **merges into ENH-01** (incremental L4 synthesis): both rewrite the same regeneration path; fixing atomicity wholesale now would be redone by ENH-01 | no | Deferred (ENH-01) |
| 16 | `compile_pipeline-5` — L2 checkpoint-resume is unreachable dead code (checkpoints written only inside the branch requiring them to exist) | P3 | `knowledge_units.py:378-419`, `compile.py:316` | independent | **yes — blocking** (Q2: delete vs complete) | B3 |
| 17 | `retrieval_context-2` — `context_expand` double-subtracts the expansion reserve, so every advertised `next` handle is refused at the same `limit_tokens` | P2 | `context_service.py:478-486`, `:765` | independent; the only finding that makes a *shipped default* (`--limit-tokens 8000`) do nothing useful | no | B4 |
| 18 | **CAND-01** — `wiki lint --fix` swallows `search.update_index` failure with bare `except Exception: pass` | P2 | `lint.py:1326-1329` | the archetype of the §32 class; `retrieval_context-5`'s logging half is the same class | no | B4 |
| 19 | **CAND-02** — `llm_identity.py:60,89` broad `except Exception: pass` with no reason/logging | P3 | `llm_identity.py` | same class as #18 | no | B4 |
| 20 | `retrieval_context-5(a)` — the two silent swallow sites in the query expander (no logging at all) | P2 | `query_expander.py:140-159`, `expansion.py:97-101` | **duplicate of the CAND-01/02 class** — the critic explicitly says "expect a duplicate and merge rather than fix twice" | no | B4 |
| 21 | `retrieval_context-5(b)` — `retrieval_trace.expansion.used` is the *config-time* decision, so a runtime expander failure is reported as a successful recovery expansion with empty `warnings` | P2 | `engine.py:270-274, 368-377` | the trace-semantics half; changes a documented field's meaning (SEARCH_ENGINE §8) | **yes** — `used` semantics + new `attempted` key | B5 |
| 22 | `retrieval_context-3` — snapshot closure omits search/index epoch, derived-state epoch, real model identity, and `created_at` | P2 | `context_service.py:136-178` | **must land before** #23 or the recomputation ships blind | **yes** — §31.3 "creation time" must be declared excluded from the digest; hard/soft component tiering (Q6) | B5 |
| 23 | `retrieval_context-1` — `context_expand`/`context_verify` never recompute the snapshot; the conflict check is a tautology against the pack's own stored id | P2 | `context_service.py:744-750`, `:869-872`, `:1053-1063` | depends on #22 | yes (tiering, Q6) | B5 |
| 24 | `retrieval_context-4` — §30.2 `policy` block, four §31.5 item fields and `coverage.contradictions_present` never emitted; `layer` is a verbatim copy of `kind` | P2 | `context_service.py:101-121, 433-457, 665-668`; `evidence.py:219-224`; `engine.py:350-355` | **deepens CAND-04**: both are "the evidence item lies about itself". CAND-04 = the locator's *truthfulness*; RC-4 = the item's *completeness* and a mislabeled `layer`. They edit the same two functions (`evidence._build_locator`/`_search_hits`, `context_service._item_payload`/`_locator_from_span`) and both force a `contract_version` bump — splitting them would bump the contract twice. | **yes** — `layer` value domain (`L1..L4`), `detail` key reconciliation, contract bump | B5 |
| 25 | **CAND-04** — `locator_status` derived from DB metadata only; `exact` fabricated without file/heading verification; `duplicate_anchor`/`stale`/file-level `unavailable` never emitted; `block_id` always `None` | P2 | `retrieval/evidence.py::_build_locator`, `context_service.py::_locator_from_span` | deepened by #24 (see above) | **yes — blocking** (Q3: implement §29 resolution vs amend §29 to a DB-metadata contract) | B5 |
| 26 | **CAND-06** — sidechat always passes the vault ROOT as `workspacePath`; the workspace KRS curation lens is inert for the whole chat surface; a root `curate.yml` would silently bind | P2 | `ChatSidebarView.ts:1868` | independent; no new finding touches it. Note it is *adjacent* to #24's `policy` block: once RC-4 emits `policy.applied_filters`, an inert lens becomes visible as an empty filter set — B5 makes CAND-06 diagnosable, B6 fixes it | **yes — blocking** (Q7: binding rule) | B6 |
| 27 | `sync_db-1` **Half B** — per-index merge rules + remote→local id remapping for `graph_entities(canonical_name,entity_type)`, `source_spans(source_id,content_hash)`, `entity_aliases` | P1 (same root as #5) | `db_sync.py`, `db/schema.py:290, 368, 445` | the half that must **not** be hot-patched: an id remap that misses one referencing column silently produces a second generation of dangling rows | **yes — blocking** (Q4: `sync_key` = immutable birth identity vs derived mirror of `relpath`) | B7 |
| 28 | `sync_db-5` — mutable-row LWW has no tie-break; a same-second concurrent edit diverges until the next edit | P3 | `db_sync.py:1366-1371` vs `:1381-1390` | **sequence after #27**: shared row ids are what make ties reachable at all, and #27 is what creates shared ids | **yes** — §13.1 currently *blesses* the mutable skip; this is a spec design gap, not a code bug | B7 |
| 29 | **CAND-05** — SCHEMA §7 MCP payload examples stale vs `mcp/server.py` (`l4_complete`/`relpath`/`source`, `ok` wrapper, `deepseek`/`ollama` keys) | P3 | `docs/specs/curator_schema/SCHEMA.md` §7 | docs-only; the sole survivor of the domain-6 sweep that never ran | no | B4 (docs rider) |

### 1.2 Supersede / deepen map (explicit)

- **RC-4 deepens CAND-04.** Neither supersedes the other. CAND-04 asks *"is this
  locator honest?"*; RC-4 asks *"is this item complete and correctly labeled?"*.
  They share `evidence.py`'s `EvidenceItem` construction and `context_service.py`'s
  `_item_payload`, and each on its own forces a pack `contract_version` bump. Shipping
  them apart bumps the contract twice for one surface. **Merged into B5 as one change.**
- **RC-5(a) is a duplicate of the CAND-01/CAND-02 class**, per the retrieval critic's
  own instruction ("expect a duplicate and merge rather than fix twice"). Its logging
  half moves into the §32 batch; its trace-semantics half (RC-5(b)) stays with
  retrieval because it changes a documented trace field's meaning.
- **CAND-03 is the specific case of sync_db-1(b)'s general disease** — a per-file
  error that makes every retry fail forever, contradicting §13.1's "retry is safe".
  `shutil.move` fixes the instance; "record the bad peer, continue, checkpoint the
  good ones" fixes the class. **Both in B2.**
- **CP-1, CP-3(b) and CP-4 are three faces of one primitive**: `sources.layer_error`
  is simultaneously a human-readable error string and pipeline control flow, and
  `set_source_layer_status` unconditionally rewrites it (`db/sources.py:523-527`).
  One primitive fix (an `UNSET` sentinel + a marker-preserving recovery predicate +
  an error-only writer) collapses all three. **B3 is organized around that primitive,
  not around the three symptoms.**
- **CP-2 splits.** The freeze (`synthesis.py:113-122`) is ~3 lines, is where the
  permanent damage lives, and repairs already-frozen vaults; the atomicity half
  touches three `db/_entities.py` signatures pinned by `test_db_public_api.py`, does
  not repair an already-frozen vault, and would be rewritten by ENH-01 anyway.
  **Freeze → B3; atomicity → ENH-01.**
- **No new finding supersedes CAND-05 or CAND-06.** CAND-05 rides B4 as a docs-only
  item; CAND-06 gets its own batch because its fix is a *product* decision about
  which workspace binds, not a defect patch.

---

## 2. Release Batches

Bump rules applied verbatim from `CLAUDE.md` §"Batch & Version Planning": Patch =
backward-compatible fix, no new user-facing capability, no schema/contract change
(a batch whose changelog carries only `### Fixed`). Minor = any new user-facing
surface, new field, or schema/contract change — and, per the task framing, **any fix
that requires amending a spec sentence is a contract decision, hence Minor**, with
one narrow exception stated in §2.8.

Versions assume the current release is **v0.42.1** and are assigned in the
recommended execution order (§4), so the numbering and the sequence agree.

### B1 — `v0.42.2` (patch) — Plugin lifetime & teardown correctness

| Item | Sev | Change |
|---|---|---|
| `plugin_lifecycle-1` | P2 | `return await this.completeViaCli(...)` at `LLMClient.ts:1250` **and** the identical 401/403 fallback at `:1318`, so the `finally` runs on settle. Regression test drives `complete()` against a stubbed CLI provider with an owner signal and asserts the child-process signal aborts — **behavior, not source text**. |
| `plugin_lifecycle-3` | P2 | Per-subdir sweep behind an age guard (skip run dirs younger than the CLI `--print-timeout`), **not** a directory relocation. §2.1.3 gains an explicit staleness definition. |
| `plugin_lifecycle-2` | P3 | Store the attach-time window (`this.repositionWin`, mirroring `dragState.win`) and detach against it; reorder `handleSelectionChange` to `removeButton()` before reassigning `activeDoc`; extend the existing ordering test to cover `handleSelectionChange`. |
| `plugin_lifecycle-4` | P3 | `private disposed = false` set in `dispose()`, clear `pending` there, early-return from `fire()`/`schedule()`/`runNow()`; add `if (this.unloaded) return;` as the first statement of the `onLayoutReady` callback (covers the orphaned watcher too). Add the missing `dispose()` unit test. |

**Bump rationale — patch.** Plugin-only, changelog is `### Fixed` only, no schema, no
migration, no `MAJOR.MINOR` spec-title bump. The plugin critic reached the same
conclusion independently. The §2.1.3 staleness sentence is a *definition of an
already-promised behavior* ("stale dirs are swept on plugin load" already exists;
"stale" was simply never defined), not a new contract — this is the §2.8 exception.

**Why it ships first:** zero cross-module dependencies, zero user decisions, four
independently revertible edits, and it retires the two P2s that are reachable on the
default provider path (`shouldUseCli` is true for antigravity/claude/codex).

**Rejected inside this batch:** relocating `chat_images` under
`vaultMachineCacheDir()` in the same change (would force re-verification of
`sandboxWrapper` write-roots and `--add-dir` generation — a second, riskier change
riding a patch); PL-4's "move the teardown registration" (unreachable after
`onunload`) and "re-read `this.syncWatcher` post-layout-ready" (already the code's
behavior).

### B2 — `v0.43.0` (minor) — Cross-device sync integrity: truthful import & durable state

| Item | Sev | Change |
|---|---|---|
| `sync_db-1` Half A | **P1** | `_do_insert` returns `rowcount`; `_lw_upsert`/`_lw_upsert_source` branch on it; a swallowed insert becomes an explicit third outcome `"conflicted"` on a new `ImportStats.conflicted` counter, surfaced in the autosync report. `import_all_peers` catches a per-file failure, records it, and **continues to the next peer**, writing `write_sync_state` in a `finally` so good peers keep their checkpoints. |
| CAND-03 | P2 | `shutil.move` (copy+unlink) instead of `Path.rename` in `_archive_conflict`. |
| `sync_db-2` | P2 | Single `_TRIGGER_BODIES` mapping rendered by both `SCHEMA_SQL` composition and `_refresh_current_triggers`; `_triggers_need_refresh` compares `sqlite_master.sql` against the normalized rendered body instead of a substring allowlist; raw string / `char(92)` for the separator. Test asserts the escape in the **installed** trigger of a `connect()`-created DB. |
| `sync_db-3` | P2 | Capture the stamp *before* `export_knowledge` in `export_for_device` (two lines, no cross-module contract). |
| `sync_db-4` | P3 | Hold one `durable_io.locked_path(state_path)` for the whole `autosync` pass, always re-read state inside the lock, write through `durable_io.atomic_write_text`. This closes the identity race, the lost update, **and** `sync_db-3`'s overlapping-export half in one change — which is why -3 and -4 batch together despite -4's P3. |

**Bump rationale — minor.** Three contract-visible changes: (a) the import outcome
vocabulary gains `conflicted` and the autosync report gains a field, which §13.1 and
§32 must state; (b) `sync_db-2`'s fix changes the *value* of `sync_key` for any
backslash `relpath` already in a DB, which is a stored-identity change SCHEMA §11.17
must describe (and which needs an explicit answer to Q5 — rewrite existing rows or
leave them); (c) `durable_io` becomes load-bearing for sync state, which §13.3 should
say. Minor also forces the four spec-title `(vX.Y.Z)` bumps per `CLAUDE.md` step 10 —
budget for that.

**Why it ships second (immediately after the no-decision patch):** `sync_db-1` is the
only **P1** in the inventory and the regression-audit P10 gate says *"Close only with
no P0/P1"*. It is also self-contained: nothing in B3–B7 depends on it, and it depends
on nothing.

**Deliberately excluded:** the identity merge (`sync_db-1` Half B) and the LWW
tie-break (`sync_db-5`). Half A converts a silent drop into a *reported* conflict —
correct and shippable today. Half B decides how two devices' rows for the same real
thing become one row, touches six referencing columns, and needs a `sync_key`
semantics ruling; hot-patching it is exactly the anti-pattern `CLAUDE.md`'s Review
Feedback Loop rule warns about. See B7.

**Rejected alternative:** `INSERT OR REPLACE`. It trades a silent drop for a silent
overwrite of the local row — the same §32 lie with a different victim.

### B3 — `v0.43.1` (patch) — Compile-status truthfulness (`layer_error` de-overload)

| Item | Sev | Change |
|---|---|---|
| `compile_pipeline-1` | P2 | `recover_stale_jobs`: `SET l2_status='pending', layer_error = CASE WHEN layer_error LIKE 'post-publish projection%' THEN layer_error ELSE NULL END` — `LIKE`, not `=`, so the `_POST_PUBLISH_PROJECTION_ERROR` prefix form `compile.py:302` accepts also survives. Keep the `l2_status='pending'` reset (§4.1 L237-239 requires it and the pending-marker disjunct does not test `l2_status`). Regression test inserts `db.recover_stale_jobs(vault.state_db)` between the simulated crash and the retry and asserts the generation id is unchanged and `_NoCallClient` is never called. |
| `compile_pipeline-3(b)` | P2 | `set_source_layer_status` gains an `UNSET` sentinel default so a status-only write leaves `layer_error` untouched; stop asserting "synthesis not attempted" when `errors` came from the synthesis step. |
| `compile_pipeline-4` | P2 | **Delete the promotion.** `_mark_clean_sync_status` clears `layer_error` only (matching its own docstring) and leaves `l3_status`/`l4_status` alone — they are already terminal and correct from `compile_global_l3`. This removes the last filesystem glob from status computation, which is the actual §26.3 requirement. Needs the error-only writer — the third consumer of the same sentinel primitive. |
| `compile_pipeline-2(a)` | P2 | Replace the per-node dep-hash short-circuit with a `synthesis_manifest`-style commit marker written **after** the loop, so a partial layer is self-identifying; **and force `reemit_synthesis` on unfreeze**, because the failure leaves the old full `SYN-*.md` on disk against a truncated DB. |
| `compile_pipeline-5` | P3 | Executes **Q2**. Recommended: delete the `if resume:` branch, the `resume` parameter, `has_l2_checkpoints`/`insert_l2_checkpoint`/`get_l2_checkpoint_hashes`, and the four bypassing tests; leave the now-unused `l2_checkpoints` table inert and drop it in B7's migration (avoids a migration for a hygiene deletion). |
| `compile_pipeline-3(a)` | P2 | **Blocked on Q1.** If the user amends §4.1 → doc change, batch stays patch. If the user rules that code must set `l4_status='error'` → an observable status value changes (it is returned by `check_source_status`), the pinned test is inverted, **and this batch becomes minor**. |

**Bump rationale — patch, conditional on Q1.** Every other item makes code match an
existing spec sentence: §26.3's marker survival, §26.3's "never promoted to authority
merely because a file was written", §27.8/§4.1's status semantics. No new field, no
migration, no new surface. The one item that can flip the bump is Q1, which is why it
must be answered **before** coding starts.

**Rejected alternatives:** (a) recomputing the grounding sets inside
`_mark_clean_sync_status` via a shared `_source_ids_for_span_ids` helper — it
duplicates compile-time policy into the sync command and creates a second place where
§4.1 can drift; deleting the promotion is smaller and strictly safer. (b) Giving the
publish-pending phase a dedicated column or a `compiler_generations.status` value now
— that is a migration and a minor bump for a one-line crash-window fix; it is the
right *eventual* shape and is parked in B7's migration window. (c) Threading a
caller-owned `conn` through clear/upsert/record to make the L4 swap atomic — correct
but expensive, does not repair an already-frozen vault, and is rewritten by ENH-01.
(d) "Making the resume path reachable" casually — the critic is explicit that half-
completing it is worse than the dead code, because an all-skipped resume returns an
empty `list_staged_unit_ids_for_source` and would publish a zero-unit generation,
retiring the source's entire authoritative unit set under §26.3's guard.

### B4 — `v0.43.2` (patch) — Observable degradation & budget correctness

| Item | Sev | Change |
|---|---|---|
| `retrieval_context-2` | P2 | In `_budget_payloads`, stop re-withholding the reserve: enforce `already_used + cost <= limit_tokens`. Regression test: fetch at limit L with a non-empty `next`, expand at the same L, assert the first handle is admitted. |
| CAND-01 | P2 | Propagate a warning to the `wiki lint` CLI surface instead of `except Exception: pass` (same pattern as the v0.36.1 MCP refresh-warning fix). |
| CAND-02 | P3 | Reason comment + module `debug` log, or narrow to `(OSError, ValueError, KeyError)`. |
| `retrieval_context-5(a)` | P2 | `logger.warning(..., exc_info=True)` at `query_expander.py:152,157` and `expansion.py:100`. **Do not change the expander's return contract** — `test_query_expander.py:39-52` pins `exp("q") == {}` on both paths, and returning a typed object breaks two passing tests for no benefit. |
| CAND-05 | P3 | Refresh SCHEMA §7 MCP payload examples (English first, then any KR mirror). |

**Bump rationale — patch.** All `### Fixed` plus one docs refresh. RC-2 restores
behavior §31.1 already mandates and needs no `contract_version` bump. The logging
items add no surface — §32 already requires the reason and the log; today's code
simply does not do it.

**Why these ride together:** they are the four cheapest, most independently
revertible changes in the inventory, and RC-2 is the one finding that makes a shipped
default path (`--limit-tokens 8000` on both `context fetch` and `context expand`) do
nothing useful — it should not wait behind the B5 contract work.

**Precondition (soft):** the `exception_hygiene` sweep never ran. B4 fixes three known
instances; it does **not** close the class. See Gate G0.

### B5 — `v0.44.0` (minor) — Context pack contract v2: snapshot closure, live conflict, evidence fidelity

| Item | Sev | Change |
|---|---|---|
| `retrieval_context-3` | P2 | Widen the closure to the fixture's own shape — `source_epoch`, `db_epoch`, `search_epoch`, `dependency_epoch`, `policy_hash`, `model_config_hash`, `tokenizer_id`, `created_at` — reusing `_hash_epoch_rows` so §31.3's "compact deterministic counts plus ordered hashes" still holds. **Tag each component hard/soft in the closure itself.** Amend §31.3 to state that creation time is recorded but excluded from the digest. |
| `retrieval_context-1` | P2 | Persist the request closure (`mode`, `source_key`, `workspace_path`, `policy_hash`) inside `context["snapshot"]`, then recompute in `context_expand`, `context_verify` **and** `context_feedback`; hard conflict on `source_epoch`/`db_epoch`/`policy_hash`, disclosed drift on `search_epoch`/`dependency_epoch`/`model_config_hash`. Add per-handle `record_hash` revalidation before serving an expanded item. |
| `retrieval_context-4` | P2 | Map `kind → layer` as `L1`/`L2`/`L3`/`L4` (matching `context_fetch_pack.json`, **not** `01_Contexts`-style folder names), threading `EngineHit.record_type` into `EvidenceItem` for `search_hit` and emitting `"unknown"` when unresolvable. Add `ranking` (thread `EngineHit.contributions` — same one-line plumbing as `record_type`, so schedule them as one task), `route_reason`, `dependency_ids`, `contradiction_state`, `coverage.contradictions_present`/`omission_categories`, and the top-level `policy` block. **Reconcile the existing `detail` key before adding anything named `detail_level`.** Make `context_verify` stop returning hardcoded `[]`. |
| CAND-04 | P2 | Executes **Q3**: either implement file-level locator resolution (existence, heading/anchor scan, hash comparison, duplicate detection, real `block_id`) or amend §29.3/§29.4 + SEARCH_ENGINE §12.2 to the DB-metadata contract and restrict clickability accordingly. Deepened by RC-4; same functions, same contract bump. |
| `retrieval_context-5(b)` | P2 | Record the outcome on `ExpandedQuery` (`expander_error`, `expander_contributed`); drive trace `expansion.used` from `expander_contributed`, keep the config-time value under a new `expansion.attempted` key so the §8 shape stays legible; append `query_expander_unavailable: <ExcType>: <msg>` to `warnings` whenever `use_expander` was true and nothing was contributed. |
| **Fixture-driven contract test** | — | **Invert `test_context_fetch_fixture_pins_pack_contract`**: assert every key present in the fixture item is present in **live** `context_fetch`/`context_expand` output, plus a value-level assertion that `layer` matches `^L[1-4]$`. Bump the pack `contract_version` (`:614`, `:653`). |

**Bump rationale — minor.** New snapshot fields, a changed `layer` value domain, new
item and coverage fields, a new trace key, a redefined trace field, a
`contract_version` bump, and two spec amendments (§31.3 creation time; §29 locator
reconciliation). This is unambiguously a contract release.

**Ordering inside the batch is load-bearing:** closure (RC-3) **before** recomputation
(RC-1), or the recomputed id is blind to index and derived-state churn and RC-1 ships
as theatre.

**This batch needs its own Arena plan.** It is the largest contract surface in the
inventory, it carries two blocking user decisions (Q3, Q6), and it is where a
half-measure is most expensive. Per `CLAUDE.md` Step 4 it gets the full treatment:
problem statement → persona proposals → cross-critique → master plan.

**Highest-value cross-cutting note, preserved verbatim from the retrieval critic:**
`docs/specs/system_behavior/context_service_fixtures/*.json` is the most valuable
artifact in this domain and is currently near-inert — loaded by exactly one test that
validates the *fixture* against a hand-written subset instead of validating the *code*
against the fixture. Three of the five retrieval findings would have been caught at
authoring time by one test asserting live output against those files. **Make that test
a deliverable, not a side effect** — it is the only change here that prevents the next
drift.

### B6 — `v0.45.0` (minor) — Workspace curation binding for chat surfaces

| Item | Sev | Change |
|---|---|---|
| CAND-06 | P2 | Executes **Q7**. Derive the active note's ancestor workspace (nearest `curate.yml`) and pass it, or pass `""` so "default" is explicit; fix the misleading comment at `ChatSidebarView.ts:1868`; decide and document what a vault-root `curate.yml` means. Spec: §9.1 / §16.1 clarification of what binds a chat turn to a workspace. |

**Bump rationale — minor.** The KRS curation lens starts *actually applying* to chat
turns. Answers change. That is a new user-facing behavior, not a fix, even though its
origin is a defect report.

**Why it ships after B5, not before:** B5's `policy` block (`applied_filters`,
`excluded`) is what makes "the lens is inert" *visible* to a user or an MCP agent.
Shipping B6 first means changing which knowledge the chat sees with no instrument to
confirm the new binding is right. B5 → B6 gives the fix an observable before/after.

### B7 — `v0.46.0` (minor, migration-bearing) — Sync identity merge & convergence

| Item | Sev | Change |
|---|---|---|
| `sync_db-1` Half B | P1 root | Per synchronized secondary UNIQUE index, declare the merge rule and implement remote→local id remapping the way `sources` already does for `sync_key`: `graph_entities` on `(canonical_name, entity_type)` → identity-merge, then rewrite `graph_relations.source_entity_id`/`target_entity_id`, `graph_relation_supports`, `entity_aliases.entity_id`, `entity_merge_proposals`, `entity_resolution_lineage`; `source_spans` on `(source_id, content_hash)` → identity-merge, then rewrite `claim_supports.source_span_id` and the JSON `source_span_ids` lists on `graph_entities`/`knowledge_units`; `entity_aliases` → merge or skip-and-report (no inbound references). |
| `sync_key` semantics | — | Executes **Q4**. Today `sync_key` is set only `AFTER INSERT` while two paths mutate `relpath` afterwards (`source_tools.py:378`, `ingest_raw.py:2267`) — it is neither an immutable birth identity nor a derived mirror. Rule (i) → import merges on `relpath` as a documented fallback before inserting; rule (ii) → add an `AFTER UPDATE OF relpath` trigger + migration. SCHEMA §11.17 must state which. |
| `sync_db-5` | P3 | Docs-first: extend §13.1 so a mutable-row exact-timestamp tie with unequal payloads uses the same deterministic canonical-JSON tie-break as the immutable path, counted as a distinct `tie_broken` statistic (§32 observability); then change `_lw_upsert`. Raise `_now_iso()` to millisecond precision (matching `sources_touch_updated_at`, `db/schema.py:731-736`) as the cheap complement — **a probability reduction, not a convergence guarantee**, and the spec text must not pretend otherwise. |
| Migration riders | — | Drop the inert `l2_checkpoints` table (if Q2 = delete); optionally de-overload `sources.layer_error` with a dedicated publish-pending column or `compiler_generations.status`, deferred here from B3. |

**Bump rationale — minor with a migration.** Schema change, contract change, and a
data-shape decision. Per `CLAUDE.md` step 2 this batch **MUST** ship a data migration
script.

**Why last:** it depends on B2 (Half A's outcome plumbing is the substrate), it is the
only batch with a migration, and `sync_db-5` is only reachable *after* Half B makes
shared row ids common. **This batch needs its own Arena plan** — an id remap that
misses one referencing column silently produces a second generation of dangling rows,
which is a P0-shaped failure introduced by a P1 fix.

**Required regression tests (from the sync critic, preserved):** (a) two devices, same
file, distinct `SPAN-` ids → `SELECT COUNT(*) FROM claim_supports WHERE source_span_id
NOT IN (SELECT id FROM source_spans)` must be `0`; (b) two devices, same
`(canonical_name, entity_type)`, distinct `ENT-` ids → no orphan `graph_relations`;
(c) `stats.inserted` must never exceed the rows actually present after the pass;
(d) a peer whose `sources` row conflicts on `relpath` must be reported **and the next
peer file must still import and checkpoint**.

### 2.8 The one bump exception applied

`plugin_lifecycle-3` requires touching PLUGIN_SCHEMA §2.1.3, yet B1 is classified
patch. The rule used: **amending a spec sentence that promises a behavior nobody can
currently verify, in order to define an undefined term in it, is a clarification, not
a contract change.** §2.1.3 already says stale `chat_images/*` dirs are swept on
plugin load; it never defined "stale". Defining it as "older than the CLI print
timeout" adds no surface and removes no promise. Every other spec touch in this plan
changes what a caller may rely on and is therefore Minor. If the user disagrees with
this line, B1 becomes `v0.43.0` and everything downstream shifts — say so in the Q&A.

---

## 3. Roadmap Merge — ROADMAP items 1 + 2 → one milestone

**Proposed replacement for ROADMAP items 1 and 2:**

> **1. v0.42.2 → v0.46.0 System Integrity Consolidation** (single milestone)
> Closes the v0.32 regression audit (P10) and the System Stability Overhaul umbrella.
> Batches B1–B7 as sequenced in `.agents/plans/system_defect_audit_arena/03_synthesis.md`.
> Plans `01_system_stability_overhaul.md` and `02_v032_regression_audit.md` are
> superseded and deleted on closure; Git retains them.

### 3.1 How regression-audit P10 closes

P9's rule is *"Fix newly confirmed findings in the smallest matching patch"* and its
closure gate is *"no P0/P1 and every P2 fixed or explicitly queued with reason."*
Mapping:

- **No P0** in the inventory. **One P1**: `sync_db-1`. Its user-visible damage
  (silent row loss reported as success, plus the permanent peer-chain wedge) is
  retired by **B2 Half A**; the deeper convergence work is **explicitly queued with
  reason** as B7. That satisfies the gate literally: the P1 *failure mode* is closed
  in B2; what remains queued is a P2-shaped improvement (merge policy) on the same
  code.
- **Every P2 is either fixed (B1–B5) or explicitly queued with a written reason**
  (CP-2(b) → ENH-01; CAND-04 and CAND-06 → B5/B6 pending user decisions).
- **P10's per-patch discipline is unchanged and applies to each batch**: docs-first,
  failing tests first, full local gates (`scripts/backend-check pytest|ruff|mypy`,
  `npx vitest run -c ./plugin/vitest.config.ts`), isolated testbed + Reference Mode
  smoke, version/changelog consistency, push, PR, latest-head CI.
- **Closure point:** after B2 merges (last P1 gone) the audit's *gate* is met; the
  plan and its evidence ledger are deleted then, and the remaining batches continue
  under the consolidated milestone. If the user prefers a single closure at the end
  of B7, that is Q10.

### 3.2 Stability-overhaul workstreams — disposition

| Workstream | Disposition | Reason |
|---|---|---|
| **1. Release-chain integrity (P6–P10)** | **Closes through B1 + B2** (+ per-batch gates for B3–B7) | P9 dry passes already ran (2026-08-04); the arena *is* the newly-confirmed-findings pass P9 asked for. The last P1 dies in B2. |
| **2. Prompt architecture v2** (golden fixtures, cross-provider output-shape metric, prompt-profile versioning, boundary normalization) | **Icebox, with an explicit re-entry trigger** | Four inspectors across four domains produced **zero** prompt-shape defects, and the briefing's measured facts show the dominant cost is the provider handshake (8.2–12.2 s), which prompt versioning cannot touch. Building a cross-provider shape harness now is speculative infrastructure ahead of a confirmed failure — exactly what `CLAUDE.md` §3 "Simplicity First" forbids. **Trigger to un-ice:** the first USER_REPORT item where a provider returns a structurally wrong payload that a fixture would have caught. **Partial credit:** B5's inverted fixture test establishes the *pattern* (fixture is the contract, code is validated against it) that a prompt harness would reuse — so the idea is not lost, only its speculative build-out. |
| **3a. Broad-exception hardening** (the §32 half) | **B4 for the known instances; the *class* stays open behind Gate G0** | CAND-01, CAND-02, `retrieval_context-5(a)` are fixed in B4. But the `exception_hygiene` inspector never ran, so B4 must not be reported as closing the workstream. G0 (§6) schedules the sweep. |
| **3b. Safe god-file decomposition** | **Icebox, with a counter-evidence note** | No confirmed defect in this arena traces to file size; all 19 are logic/contract bugs. The honest counter-evidence: `LLMClient.ts` carried PL-1 + PL-3 (+ undebated F2/F3/F4) and `compile.py`/`commands/common.py` carried CP-1/CP-3/CP-4 — defect clustering, which is weak evidence *for* extraction. But a characterization-then-extract program is a large, high-churn change competing with a live P1, and `CLAUDE.md` §3 (Surgical Changes) says don't refactor what isn't broken. **Trigger to un-ice:** a third *new* defect in the same file region after B1/B3 land. |
| **4. Measured performance** | **Closed as a workstream; its only surviving descendant is ENH-01** | Already measured and closed in USER_REPORT (2026-08-04 10:55): the bottleneck is the provider service handshake, which Incurator cannot shorten; the briefing forbids re-deriving it. What remains is **cost**, not latency: ENH-01 incremental L4 synthesis (wholesale regen today), which becomes a **deferred milestone** and carries `compile_pipeline-2(b)`'s atomicity half with it. |
| **5. Existing-surface UX** | **Dissolve the umbrella**; two concrete items map to batches, the rest routes through USER_REPORT triage | Concrete: (a) B3's CP-4 removes a false `done` promotion, so users will start seeing honest `skipped` statuses — the dashboard/`wiki status` surface must explain `skipped` vs `done` or the fix reads as a regression (Q9); (b) B6 should surface *which* workspace bound a chat turn. Everything else in "chat, popover, diff, dashboard friction" is unenumerated. An umbrella with no enumerated items is a permanent open roadmap row that never closes; per the pipeline state machine, UX friction should enter as USER_REPORT items and be batched like any other report. |

### 3.3 Enhancement candidates (context, not defects)

ENH-01 becomes a **deferred milestone** (carrying CP-2(b)); ENH-02 (PPR local
expansion) and ENH-03 (DRIFT explore trees) remain **deferred to Program 3** per
§20.1/§27 — the arena is the evidence they stay worth doing, not a reason to pull
them forward; ENH-04 (passive related-concepts sidebar) and ENH-05 (community-
hierarchy dashboard view) are **read-only surfaces with no new backend state** and are
the natural pairing for the UX work in Q9 — recommend they enter USER_REPORT-driven
triage rather than this milestone.

---

## 4. Sequence, Risk, and Decision Gates

```
G0 ──▶ B1 ──▶ B2 ──▶ B3 ──▶ B4 ──▶ B5 ──▶ B6 ──▶ B7
(gap)  0.42.2 0.43.0 0.43.1 0.43.2 0.44.0 0.45.0 0.46.0
       patch  MINOR  patch  patch  MINOR  MINOR  MINOR+migration
```

| Order | Batch | Risk | Depends on | **Decision needed BEFORE coding** |
|---|---|---|---|---|
| G0 | Adjudicate plugin Pass A F1–F4; run the two missing sweeps | none (read-only) | — | **Q8** (do it, or accept the gap and close) |
| 1 | **B1** plugin lifetime | low — plugin-only, 4 revertible edits, no backend | — | none (unless the user rejects the §2.8 bump exception) |
| 2 | **B2** sync integrity | **medium-high** — touches the import path every device runs; but it is the only P1 | — | **Q5** (`sync_key` value rewrite for existing backslash rows), **Q6b** (Windows locking) |
| 3 | **B3** compile status | medium — one primitive, three call sites, one deletion | — | **Q1** (l4 `error` vs `skipped` — *flips the bump*), **Q2** (delete vs complete resume) |
| 4 | **B4** degradation + budget | low — smallest change set in the plan | — | none |
| 5 | **B5** context pack v2 | **high** — largest contract surface; needs its own Arena plan | B4 (RC-2 must not be entangled with the contract bump) | **Q3** (CAND-04 locator: implement vs amend §29), **Q6a** (hard/soft conflict tiering) |
| 6 | **B6** workspace binding | medium — changes which knowledge chat sees | B5 (needs the `policy` block as the observable) | **Q7** (binding rule + root `curate.yml` meaning) |
| 7 | **B7** identity merge | **highest** — migration + six referencing columns; own Arena plan | B2 | **Q4** (`sync_key` semantics), **Q11** (§13.1 mutable tie-break) |

**Decisions that must be answered before any coding starts (they change scope or
bump):** Q1, Q2, Q3, Q4, Q5, Q6, Q7. Recommend collecting all of them in one pass at
milestone start rather than blocking each batch in turn.

**Severity-vs-order tension, stated openly.** B2 carries the only P1 yet ships second,
behind a patch. Rationale: B1 needs no decisions and can be coded and merged while the
Q5/Q6b answers are pending, so putting it first costs the P1 nothing in wall-clock.
**If the user wants the P1 mitigated immediately**, `CLAUDE.md`'s HOTFIX EXCEPTION
supports carving out the two lowest-risk pieces of B2 Half A — *"continue past a bad
peer, keep good checkpoints"* + *"never report a swallowed insert as `inserted`"* —
as `hotfix/v0.42.2-sync-import-truthfulness` ahead of everything, deferring the
`conflicted` counter's spec text to B2. That is Q12.

---

## 5. Rejected Alternatives (recorded so they are not re-litigated)

1. **One mega "stability" batch.** Violates the overhaul plan's own gate
   ("independently reviewable releases"), mixes patch and minor bumps into a single
   version decision, and makes a rollback of any one fix a rollback of all 22.
2. **`INSERT OR REPLACE` for `sync_db-1`.** Trades a silent drop for a silent
   overwrite. Same §32 lie, different victim.
3. **Recomputing grounding sets inside `_mark_clean_sync_status` (CP-4).** Duplicates
   compile-time policy into the sync command; creates a second place where §4.1 can
   drift. Deleting the promotion is smaller and strictly safer.
4. **Threading a caller-owned `conn` through the L4 rebuild as a defect fix now
   (CP-2b).** Correct shape, wrong time: it touches three `db/_entities.py` signatures
   pinned by `test_db_public_api.py`, does not repair an already-frozen vault, and is
   rewritten by ENH-01.
5. **Shipping RC-1 without RC-3.** The recomputed snapshot id would still be blind to
   index and derived-state churn — a conflict check that looks fixed and is not.
6. **Making the L2 resume path reachable without all three preconditions
   (CP-5).** Half-completing it publishes a zero-unit generation and retires the
   source's authoritative unit set under §26.3's guard — worse than the dead code.
7. **Relocating `chat_images` under `vaultMachineCacheDir()` inside the B1 patch.**
   Would force re-verification of `sandboxWrapper` write-roots and `--add-dir`
   generation; the age guard achieves the same safety with a fraction of the blast
   radius.
8. **Citing a PLUGIN_SCHEMA teardown-must-release-listeners clause for PL-2.** It does
   not exist (the critic verified: "listener" appears only at L462). If such a clause
   is wanted it must be *added*, never cited as pre-existing.
9. **Raising `_now_iso()` to millisecond precision as a substitute for the LWW
   tie-break.** It is a probability reduction, not a convergence guarantee.
10. **Bumping the pack `contract_version` twice** (once for RC-4, once for CAND-04).
    They edit the same functions and the same surface; one bump, one batch.
11. **Keeping ROADMAP items 1 and 2 as separate umbrellas.** Item 1's remaining scope
    *is* item 2's workstream 1; every other item-2 workstream is now either mapped to
    a batch, deferred with a named trigger, or dissolved. Two rows for one body of
    work is how a roadmap row becomes permanent.
12. **Declaring the §32 hardening workstream closed after B4.** B4 fixes three known
    instances of a class whose sweep never ran. See Gate G0.

---

## 6. Gate G0 — the audit gap that must be resolved before closure

Before P10 can be honestly declared closed, one of the following must happen:

- **Option A (recommended):** run three short read-only passes — (i) adjudicate plugin
  Pass A **F1–F4**, starting with F1 [P1] (Quick Query `fetchActivePdfPage` called
  without `expectedDocumentId` at `quickQueryPopover.ts:484-492`, while the identical
  local-tool call site *does* pass it at `main.ts:1859-1860`); (ii) the repo-wide §32
  `exception_hygiene` sweep; (iii) the `docs_parity` sweep (CLI surface policy §11.4,
  MCP tool list vs `MCP_USER_GUIDE`, EN↔KR sampling, README/setup accuracy). Fold any
  survivors into B4 (patch-shaped) or B1 (plugin-shaped) before those batches ship.
- **Option B:** the user explicitly accepts the gap, and the closure note records that
  domains 5 and 6 were never audited and F1–F4 were never adjudicated.

F1's adjudication should not wait for the general sweep: if it holds, it is a
wrong-knowledge defect on the Quick Query surface and belongs in **B1**, which would
make B1 the highest-value batch in the plan rather than the safest one.

---

## 7. Open Questions (user decisions only)

| # | Question | Blocks | Default if unanswered |
|---|---|---|---|
| **Q1** | `compile_pipeline-3(a)`: set `l4_status='error'` on report/synthesis failure per §4.1, or amend §4.1 (+ KR) to bless `l3='error' + l4='skipped'` as the global-failure shape? The critic recommends amending the spec (L4 is global; a per-source L4 `error` is not a real concept). **Choosing "code changes" flips B3 from patch to minor.** | B3 | amend the spec (cheaper, more honest) |
| **Q2** | `compile_pipeline-5`: delete the L2 checkpoint-resume machinery, or complete it (all three preconditions together)? Deleting forfeits a per-batch cost saving on interrupted L2 builds; completing costs a publish-transaction change plus a zero-unit guard. If delete: drop the `l2_checkpoints` table now (migration → minor) or leave it inert until B7? | B3 | delete; drop the table in B7 |
| **Q3** | **CAND-04**: implement real file-level locator resolution (existence, heading/anchor scan, hash drift, duplicate detection, `block_id`), or amend §29.3/§29.4 + SEARCH_ENGINE §12.2 to a DB-metadata contract and restrict what may render clickable? Per repo rules the divergence means both are wrong until reconciled — this is a product decision about how much a citation link is allowed to promise. | B5 | — (must be answered) |
| **Q4** | Is `sync_key` an **immutable birth identity** (import must merge on `relpath` as a documented fallback before inserting) or a **derived mirror of `relpath`** (add an `AFTER UPDATE OF relpath` trigger + migration)? Today it is neither; SCHEMA §11.17 must state which. | B7 | — (must be answered) |
| **Q5** | `sync_db-2` fix changes `sync_key` values for backslash `relpath`s. Do existing DBs get their bad `sync_key`s rewritten by migration (converging already-split rows), or left alone (no rewrite, accept historical splits)? | B2 | — (must be answered) |
| **Q6** | (a) Which snapshot-closure components are **hard conflicts** vs **disclosed drift**? Recommended: hard on `source_epoch`/`db_epoch`/`policy_hash`, soft on `search_epoch`/`dependency_epoch`/`model_config_hash`, so a routine `wiki reindex` does not cause a conflict storm. (b) `durable_io.locked_path` degrades to a `threading.RLock` on Windows (`durable_io.py:23`) — is cross-process Windows sync a supported topology? If yes, B2's lock is a no-op there and needs a real file lock. | B5 / B2 | (a) as recommended; (b) — |
| **Q7** | **CAND-06**: which workspace binds a chat turn — nearest ancestor `curate.yml` from the active note, an explicit workspace picker in the sidechat UI, or always-default with an explicit `""`? And what should a vault-root `curate.yml` mean (bind globally, or be ignored)? | B6 | nearest ancestor; root `curate.yml` ignored unless explicitly selected |
| **Q8** | **Gate G0**: run the three missing read-only passes (plugin Pass A F1–F4 adjudication, repo-wide §32 sweep, docs-parity sweep) before closing P10, or accept the documented gap? F1 is an unadjudicated **P1** claim of wrong-PDF page splicing. | closure | run them (Option A) |
| **Q9** | B3's CP-4 stops the false `done` promotion, so users start seeing honest `skipped` statuses. Does the dashboard / `wiki status` surface need an explanation of `skipped` vs `done` **in the same batch** (turning B3 into a UX change), or does the status change ship alone with a changelog note? | B3 | changelog note only; UX enters via USER_REPORT |
| **Q10** | Delete `02_v032_regression_audit.md` + its ledger after **B2** (the gate is literally met once the last P1 is gone), or hold both plans until **B7** and close everything at once? | closure | delete after B2 |
| **Q11** | `sync_db-5`: amend §13.1 to extend the canonical-payload tie-break to mutable rows (with a `tie_broken` statistic), or accept documented same-second divergence that self-heals on the next edit and ship only the millisecond-clock mitigation? | B7 | amend §13.1 |
| **Q12** | The only P1 (`sync_db-1`) ships second. Do you want a `hotfix/v0.42.2-sync-import-truthfulness` carve-out — "continue past a bad peer" + "never report a swallowed insert as inserted" — ahead of B1, deferring the `conflicted` counter's spec text to B2? | ordering | no carve-out; ship B1 then B2 |
| **Q13** | Bump-boundary ruling (§2.8): is defining an undefined term inside an existing spec sentence (PLUGIN_SCHEMA §2.1.3 "stale") a clarification (B1 stays patch) or a contract change (B1 becomes `v0.43.0` and everything downstream shifts)? | B1 numbering | clarification |
| **Q14** | Roadmap items 2's workstreams "prompt architecture v2" and "safe god-file decomposition" are recommended for **Icebox with named triggers**. Accept, or keep either as an active milestone with enumerated scope? | roadmap | Icebox both |

---

## 8. What This Plan Does Not Claim

- It does not claim the system is now fully audited: two of six domains never ran and
  four plugin findings were never adjudicated (§0, Gate G0).
- It does not claim B4 closes the §32 exception class — only its three known members.
- It does not claim the P1 is "fixed" by B2 in the convergence sense; B2 makes the
  loss **reported and non-wedging**, B7 makes replicas **converge**.
- It does not re-derive the measured performance facts (briefing forbids it) and does
  not propose any latency work: the dominant cost is the provider handshake.
- It contains no code, test, doc, or config change. Every batch below B1 still owes
  its own docs-first spec edit, failing test, local gates, testbed smoke, version
  bump, and changelog entry per the Universal Strict Workflow.

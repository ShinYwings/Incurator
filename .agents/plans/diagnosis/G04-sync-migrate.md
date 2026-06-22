# Diagnosis: G04-sync-migrate

Coverage:
- `backend/src/curator/sync.py` (1089 lines) — read in full.
- `backend/src/curator/migrate.py` (227 lines) — read in full.
- Context read to judge correctness: `constants.py` (prefixes/layers/types, `VAULT_SCHEMA_VERSION=1`), `config.py` (`MACHINE_LOCAL_CONFIG_KEYS`), `page_writer.py` (`extract_relation_targets`, `extract_wikilink_targets`, `parse_page`, `read_page`), `pipeline/projection.py` (page emission — confirms no `content_hash` frontmatter is written), `db.py` (`get_page_hashes`/`update_page_hash`), and callers in `cli.py` / `mcp_server.py`.

## Findings

### [G04-sync-migrate-1] (a) S1 — Incremental-sync fast path is dead: DAG pages never carry a `content_hash` frontmatter key
- Loc: backend/src/curator/sync.py:113-157 (`_frontmatter_content_hash`, `_find_changed_nodes`, `run_incremental_sync`)
- Evidence: `_find_changed_nodes` decides a node is changed when `not expected or expected != _hash_file_content(md_path)` (line 134), where `expected = _frontmatter_content_hash(md_path)` reads `page.frontmatter.get("content_hash")`. But the page-emission pipeline (`pipeline/projection.py` `emit_atom_markdown`/`emit_concept_markdown`/`emit_synthesis_markdown`) never writes a `content_hash` frontmatter key, and `page_writer` never adds one. A repo-wide grep shows every `content_hash` producer is the DB `sources` table, not page frontmatter. So `_frontmatter_content_hash` always returns `None`, `expected` is always falsy, and EVERY page is reported as "changed". `run_incremental_sync` therefore always returns `llm_required: True` and `changed_nodes = <all nodes>` — the "skip LLM verification when body hashes match" optimization (docstring line 140) can never trigger.
- Fix sketch: Either (1) make the projection emitters stamp `content_hash: <_hash_file_content>` into frontmatter when a page is written, then this path works; or (2) compare against the DB page-hash store (`db.get_page_hashes`) the way `scan_for_changes` already does, instead of a non-existent frontmatter field. Option (2) reuses an existing working mechanism and is lower-risk.
- Blast radius: `run_incremental_sync` is invoked from `mcp_server.py:2963` and `cli.py:4267`. Effect today is purely a missed optimization (it over-reports work, never under-reports), so it is not data-corrupting — but it defeats the entire v0.2.1 fast-sync feature and forces full LLM passes.
- Suggested PR: "fix(sync): base incremental-sync change detection on DB page hashes instead of a never-written content_hash frontmatter field".

### [G04-sync-migrate-2] (d) S2 — Dead repair branch: `concept_ids is empty` gap message is never produced
- Loc: backend/src/curator/sync.py:590-615 (`repair_structural_gaps`, L4 branch)
- Evidence: The branch guards on `gap.layer == consts.TYPE_L4 and "concept_ids is empty" in gap.message`. A grep for that substring shows it appears only at line 590 (the consumer). No producer ever emits a `VerificationGap` whose message contains "concept_ids is empty": `run_mode_a` only emits "Synthesis file unreadable." for L4 (line 307) and never inspects whether a SYN's `concept_ids` is empty; `run_mode_c` emits "Synthesis logic not fully derivable…" for L4. `repair_structural_gaps` is fed `run_mode_a` output (cli.py:1007, 4319). So this ~25-line block (including the `_body_concept_paths`/`downstream_*` reconstruction logic) is unreachable dead code.
- Fix sketch: Either add the missing producer in `run_mode_a` (emit a gap "concept_ids is empty…" when an L4 page has no `concept_ids`), which makes the repair live; or delete the branch as dead code. Verify intent against spec before deleting — the matching L3 "Relations is empty" branch (line 571) IS reachable (produced at line 322), so the L4 branch was likely meant to mirror it and the producer was simply never added.
- Blast radius: Self-contained; deleting it changes nothing observable today. Adding the producer would newly auto-rewrite SYN `concept_ids` during structural repair.
- Suggested PR: "fix(sync): wire (or remove) the unreachable L4 concept_ids structural repair branch".

### [G04-sync-migrate-3] (a/d) S2 — `repair_logical_gaps` iteration loop is a no-op; `fix_gaps` can never report `fixed`
- Loc: backend/src/curator/sync.py:931-954 (`fix_gaps`), 1029-1070 (`repair_logical_gaps`)
- Evidence: `fix_gaps` only ever does `result.unfixable += 1` and appends to `needs_review` — it never sets `fixed`, `rebuilt_downstream`, or `fixed_nodes` (by design per the v0.3.1 docstring: sync surfaces gaps, doesn't auto-rewrite). But `repair_logical_gaps` loops `for _ in range(max_iterations)` and breaks at line 1060 when `repair.fixed == 0 and repair.rebuilt_downstream == 0`, which is ALWAYS true on the first pass. So the second `run_mode_c` re-verification (lines 1062-1068) is never reached, and `max_iterations` (default 2) is dead. The per-`fixed_nodes` callback loop (lines 1051-1053) never fires. The function pays for one `run_mode_c` (line 1040), one `fix_gaps`, then breaks.
- Fix sketch: Given `fix_gaps` is intentionally non-mutating now, collapse `repair_logical_gaps` to a single verify+collect (drop the loop, `max_iterations`, and the unused aggregate counters), OR document that the loop is reserved for a future auto-repair mode. Current state is misleading: callers (cli.py:1026, 4451) pass/accept iteration semantics that do nothing.
- Blast radius: `repair_logical_gaps` is the main `wiki sync` logic-verification entry. No incorrect output today, but wasted abstraction and a misleading contract.
- Suggested PR: "refactor(sync): simplify repair_logical_gaps to match the non-mutating fix_gaps contract".

### [G04-sync-migrate-4] (c/e) S2 — Debug `print()` statements left in `apply_generative_backprop`
- Loc: backend/src/curator/sync.py:974, 977
- Evidence: `print(f"Skipping gap {gap.node_id}: layer={gap.layer}, reasoning={bool(gap.reasoning)}")` and `print(f"Checking gap {gap.node_id} reasoning: {gap.reasoning}")` are raw stdout prints inside a library function. The module otherwise uses no logging here. These pollute CLI/MCP stdout (MCP especially — stdout is the JSON-RPC channel for stdio servers) and dump full LLM reasoning text on every gap.
- Fix sketch: Replace with `logging` at debug level, or remove. For MCP stdio safety, never `print` to stdout from server-reachable code.
- Blast radius: `apply_generative_backprop` is called from cli.py:4444. If reachable over an MCP stdio path it could corrupt the protocol stream; at minimum it's noisy.
- Suggested PR: "fix(sync): drop stray debug prints in apply_generative_backprop".

### [G04-sync-migrate-5] (h) S2 — Structural/nested repairs write files directly, bypassing the DB page-hash store
- Loc: backend/src/curator/sync.py:585, 614, 637 (`con_path.write_text`/`exh_path.write_text`/`md_path.write_text`) vs. db.update_page_hash
- Evidence: `repair_structural_gaps` and `repair_nested_frontmatter` mutate page bodies and `write_text` directly, but never call `db.update_page_hash`. In `cli.py` sync flows, `repair_structural_gaps`/`repair_nested_frontmatter` (lines 1007-1008, 4319-4320) run, and `update_all_page_hashes` is only invoked inside `run_incremental_sync`, not in these structural-repair flows. After a repair, the on-disk file no longer matches the DB hash, so the NEXT `scan_for_changes` will report these repaired pages as `modified` (a false positive) and `run_mode_c` may re-verify them needlessly. There is no atomic-write either: a crash mid-`write_text` (e.g. on the multi-step `## Relations` rewrite) leaves a partially written page.
- Fix sketch: After a successful repair, call `db.update_page_hash` for the rewritten path (or run `update_all_page_hashes` at the end of the repair pass). Use a write-to-temp-then-rename pattern for crash safety, matching whatever `page_writer` does for its own writes.
- Blast radius: Causes spurious "modified" churn on the next sync and a small corruption window. Not silently destructive, but defeats hash-based skip and risks half-written pages.
- Suggested PR: "fix(sync): refresh DB page hashes after structural/nested repairs and write atomically".

### [G04-sync-migrate-6] (b) S3 — Duplicated downstream-traversal logic between Mode B helpers and `downstream_*` functions
- Loc: backend/src/curator/sync.py:403-439 (`_trace_downstream`), 442-474 (`downstream_concepts_for_atom`/`downstream_exhibitions_for_concept`/`downstream_atoms_for_context`), 485-529 (`_logical_scope_for_nodes`)
- Evidence: Three near-identical "scan a layer dir, read each page's link field, collect those that reference node_id" passes exist: `_trace_downstream` reimplements the same edge-walk that `downstream_concepts_for_atom`/`downstream_exhibitions_for_concept`/`downstream_atoms_for_context` already encapsulate, and `_logical_scope_for_nodes` calls the latter trio. Each is an O(files) full-dir glob+parse; combined they produce N+1-style repeated full scans of the Collections layers per node.
- Fix sketch: Have `_trace_downstream` delegate to the `downstream_*` helpers (single source of edge logic). Longer term, build an in-memory edge index once per sync run and reuse it across Mode A/B/C and `_logical_scope_for_nodes` instead of re-globbing+re-parsing per call.
- Blast radius: Refactor-only; behavior should be preserved. Touches the core verification helpers, so needs the existing sync tests green.
- Suggested PR: "refactor(sync): unify downstream edge traversal behind the downstream_* helpers".

### [G04-sync-migrate-7] (g) S2 — `downstream_*` and `_logical_scope_for_nodes` re-parse every Collections file per node (N+1 / quadratic)
- Loc: backend/src/curator/sync.py:442-474, 509-527, 598-606
- Evidence: `_logical_scope_for_nodes` (run once per `run_mode_c` call, and `run_mode_c` is itself called repeatedly from `repair_logical_gaps`) calls `add_atom` → `downstream_concepts_for_atom`, which globs ALL `CON-*.md` and parses each via `_concept_atom_ids` (which `read_page` + regex-scans the body) for EVERY changed atom. Similarly `repair_structural_gaps` line 598-606 nests `downstream_atoms_for_context` inside a loop over `_body_context_ids`, then `downstream_concepts_for_atom` inside a loop over atoms — a full re-scan of the atom and concept dirs per context per gap. For a vault with many nodes and multiple dirty nodes this is quadratic disk+parse cost on the hot sync path.
- Fix sketch: Build the reverse edge maps (ctx→atoms, atom→concepts, concept→syns) once at the start of the sync pass and pass them down; or memoize parsed pages within a run.
- Blast radius: Performance only; correctness unchanged. Same call sites as finding 6.
- Suggested PR: "perf(sync): precompute reverse-edge index once per sync pass".

### [G04-sync-migrate-8] (a/h) S3 — `_drop_nested_frontmatter_body` last-resort heading fallback can silently drop body content
- Loc: backend/src/curator/sync.py:696-711
- Evidence: When a body starts with `---\n` but neither the `parse_page` branch nor the regex `^---\s*\n.*?\n---\s*\n?(.*)$` matches (e.g. an unterminated nested frontmatter block, no closing `---`), the final fallback searches for the first `# ` heading and sets `page.body = body[heading.start():]`, discarding everything before the first heading. If the real content has no `# ` heading at all, none of the branches fire and the malformed `---` block is silently left in the body. The heuristic can also clip legitimate intro text that precedes the first heading.
- Fix sketch: Tighten to only strip a confirmed, properly delimited nested frontmatter block; if the block is malformed/unterminated, leave the page untouched and surface it as a gap/warning rather than guessing a cut point.
- Blast radius: Affects `repair_nested_frontmatter` and `repair_structural_gaps` (both call this). Low frequency (only triggers on already-malformed LLM output) but it mutates user-visible page bodies.
- Suggested PR: "fix(sync): make nested-frontmatter stripping conservative; warn instead of guessing on malformed blocks".

### [G04-sync-migrate-9] (c) S3 — `LLMError`-only catch in Mode C silently drops a node from verification
- Loc: backend/src/curator/sync.py:814-817, 909-912
- Evidence: `_verify_one_concept` and the Phase-2 SYN loop catch `LLMError` and `return {}, None` / `continue`, treating an LLM failure as "no result, no gap". A node that could not be verified because the model errored is silently indistinguishable from a node that passed verification — the gap list omits it, so `wiki sync` reports clean. Only `LLMError` is caught; any other client exception (timeout wrapper, JSON issue inside `client.chat`) would propagate and abort the whole pass, which is inconsistent.
- Fix sketch: On `LLMError`, record an "unverified (LLM unavailable)" gap or surface a count of skipped nodes so the user knows verification was incomplete, rather than implying success.
- Blast radius: `run_mode_c` results feed `wiki sync` health reporting. Risk is a false "all good" when the model was down.
- Suggested PR: "fix(sync): report LLM-skipped nodes in Mode C instead of silently dropping them".

### [G04-sync-migrate-10] (c) S3 — Broad `except Exception` swallows all errors in migrate config/frontmatter helpers
- Loc: backend/src/curator/migrate.py:83-84, 95-96, 132-133, 146-148
- Evidence: `get_vault_schema_version` returns `0` on ANY exception (line 83) — a transient read error or a genuinely corrupt config both silently read as "pre-migration vault", which would re-run migrations against a vault that may already be at a higher version. `set_vault_schema_version` swallows a parse failure and rebuilds `current = {}` (line 95-96), which would DROP all existing config keys when it rewrites the file. `_parse_frontmatter` and `scan_stale_collection_files` also blanket-catch. The `set_vault_schema_version` data-loss path is the notable one.
- Fix sketch: Narrow to expected exceptions (`OSError`, `yaml.YAMLError`). For `set_vault_schema_version`, do NOT proceed to overwrite with an empty dict on parse failure — abort and surface the error so a corrupt config isn't silently truncated to a single key.
- Blast radius: `set_vault_schema_version` writes `.curator/config.yml`. A parse failure mid-migration could wipe user/machine config. Low probability, high impact.
- Suggested PR: "fix(migrate): narrow exception handling and avoid clobbering config on parse failure".

### [G04-sync-migrate-11] (h) S3 — `run_migrations` version accounting breaks if a middle step is skipped
- Loc: backend/src/curator/migrate.py:203-223
- Evidence: The loop iterates `for v in range(current, target)`. A step with no registered `fn` is appended to `steps_skipped` and `continue`d, NOT counted in `steps_run`. After the loop, the new version is computed as `new_version = current + len(result.steps_run)` (line 221). If a future schema has, say, step v1→v2 missing (no-op) but v2→v3 present, `steps_run` would be length 1 while the vault has advanced 2 logical versions — the recorded `vault_schema_version` would be set to `current+1`, leaving the vault permanently one version behind and re-running v2→v3 forever. The accounting assumes contiguous runnable steps. Today only step 0 exists and `VAULT_SCHEMA_VERSION=1`, so this is latent.
- Fix sketch: Set `new_version = target` when `result.ok` and the loop completed without an early `break`; track the highest successfully-processed `v+1` explicitly rather than counting list length.
- Blast radius: Latent — triggers only when a non-contiguous/skipped migration step is introduced. Worth fixing before the next schema bump.
- Suggested PR: "fix(migrate): record target schema version by highest applied step, not steps_run length".

### [G04-sync-migrate-12] (f) S3 — Stale docstrings/type comments reference retired EXH/exhibition vocabulary
- Loc: backend/src/curator/sync.py:5-8 (module docstring "L4 Exhibitions"), 63 (`VerificationGap.layer` comment lists `'exhibition'`), 66 (`reasoning ... (Mode C only)`), 297/301/302 (`exh_dir`, `exh_id` for the synthesis dir), 442-462 (`downstream_exhibitions_for_concept`, returns "SYN IDs")
- Evidence: Per CLAUDE.md System Invariants, `EXH-` is retired and L4 is `04_Synthesis`. The code correctly uses `paths.synthesis` and `PREFIX_L4=SYN`, but the docstrings and the `layer` field comment still say "Exhibition"/`'exhibition'`, and several local vars (`exh_dir`, `exh_id`, `exhibition_files`, `downstream_exhibitions_for_concept`) keep the retired noun. This is doc/code drift that misleads future readers into thinking an exhibition layer is live.
- Fix sketch: Rename the docstrings and the `layer` comment to "Synthesis"; optionally rename the `exh_*` locals/`downstream_exhibitions_for_concept` to `syn_*`/`downstream_synthesis_for_concept` (public-rename is a wider blast radius — check `cli.py` callers first).
- Blast radius: Comments/docstrings are zero-risk. A public function rename (`downstream_exhibitions_for_concept`) needs caller updates.
- Suggested PR: "docs(sync): replace retired Exhibition vocabulary with Synthesis in sync.py".

### [G04-sync-migrate-13] (a) S3 — `_drop_nested_frontmatter_body` discards a recovered nested frontmatter instead of merging it
- Loc: backend/src/curator/sync.py:613-614 vs 696-711
- Evidence: In `repair_structural_gaps` the L4 branch calls `_drop_nested_frontmatter_body(page)` then later sets `page.frontmatter["concept_ids"]`. `_drop_nested_frontmatter_body` only strips the nested block's *text* from the body; any keys that were trapped in the nested frontmatter (e.g. a real `concept_ids` the LLM nested by mistake) are thrown away, not merged back into `page.frontmatter`. So the very data the repair is trying to reconstruct could be silently dropped before reconstruction. (`_merge_immutable_frontmatter` exists at line 684 but is never called from these repair paths.)
- Fix sketch: When `_drop_nested_frontmatter_body` parses a real nested frontmatter, return/merge its keys into the page frontmatter (respecting immutable-key precedence) instead of discarding them.
- Blast radius: Affects structural repair correctness for malformed LLM pages. Edge-case frequency.
- Suggested PR: "fix(sync): merge recovered nested-frontmatter keys instead of dropping them during repair".

## Positives (keep / do-not-break)
- `_parse_verify_response` (lines 714-735) is robust: strips code fences, tolerates malformed JSON, and falls back to a VALID/INVALID text heuristic for local/older models. Keep this resilience.
- Mode C parallelism (lines 829-853) correctly clamps `max_workers=1` for `OllamaClient` (single-request local backends) via duck-typed provider detection, avoiding a circular import — a thoughtful, well-commented guard.
- `_body_for_logic_check` (lines 672-681) trims long bodies for the LLM but deliberately re-appends the `## Relations` section so DAG edges are never truncated out of the verification prompt. Important correctness detail — preserve it.
- `run_mode_b` (lines 644-659) deduplicates gaps by `(layer, node_id, message)` preserving order — good defense against the upstream/downstream traces double-reporting.
- `migrate.run_migrations` stops on the first failing step (`break`, line 218) and only records the new version when `result.ok` — correct fail-safe so a failed migration doesn't advance the version past a broken step.
- `migrate.get_vault_schema_version` reading directly from the raw vault config file (not the merged config) is intentional and correct, matching the v0.4.1 machine-local-config separation.

## Open questions for the human
- Is the v0.2.1 incremental-sync fast path (finding 1) still a desired feature? If yes, where should the canonical page hash live — frontmatter `content_hash` (needs projection to stamp it) or the DB page-hash store (already populated by `update_all_page_hashes`/`scan_for_changes`)? This decision determines the fix for finding 1.
- Is `repair_structural_gaps`' L4 `concept_ids is empty` branch (finding 2) intended to become live (add the producer in `run_mode_a`), or is it abandoned and safe to delete?
- Is `apply_generative_backprop` (generative backprop / new-atom synthesis on logical gaps) an active feature, or experimental? Its debug `print`s and the "Removed external/absent filter" comment (line 979) suggest it's mid-development; confirm before relying on it.
- Should `repair_logical_gaps`' iteration loop (finding 3) be removed to match the non-mutating `fix_gaps`, or is auto-repair (a future `fix_gaps` that actually rewrites) planned, in which case the loop is reserved scaffolding?

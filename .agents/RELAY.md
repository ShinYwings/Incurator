# Cross-Agent Relay State

## Goal

Execute Batch 2: Plan B (Math Extraction Distillation) — Evidence Compiler
Integrity release (target v0.8.0).

## Plan Reference

- Master plan: `.agents/plans/B_math_extraction_distillation.md`
- Coding-time evidence ledger: `.agents/plans/B_roadmap_evidence.md`
- Previous plan: Plan D2 (PR #28, v0.7.0) is merged.

## Analysis And Reasoning

- Branch `feature/plan-b-math-distillation` is based on merged Program 1
  `master` (`5a3932c`) plus PM workflow chore commits.
- P0 (Program Setup And Measured Baseline) is COMPLETE: all five Program 1
  failure-atlas suites pass at the rollback anchor (135 passed, 10 xfailed —
  the strict-xfail oracles). Every P0 concern is reproduced, accepted, or
  scheduled in the ledger's failure-boundary table; none disproven. Active
  testbed scenario confirmed as `gaussian_splatting`; testbed DB backed up to
  `.agents/backups/b-pre-implementation-state.sqlite` and restoration
  verified.
- P1 (Docs-First Contract And Migration Specification) is COMPLETE: SCHEMA.md
  §20 (claim_supports, compiler_generations/GEN-, knowledge_units additive
  columns, formula_recovery metadata, audit assertions, v8 migration),
  SYSTEM_BEHAVIOR.md §26 (support/formula/generation/reconciliation/audit
  behavior + migration rehearsal and rollback acceptance criteria),
  SEARCH_ENGINE_SCHEMA.md §10 (generation-aware publish, F10 full-span
  hydration), PLUGIN_SCHEMA.md no-change note, and all four guide pairs
  (EN → KR). Spec titles stay at v0.7.0 until the P10 release bump because
  `tests/test_spec_sync.py` pins titles to the released backend version.
- Full backend CI after P1: 723 passed, 10 xfailed; ruff clean. No code
  behavior change.

## Progress Status

- [x] Fetch the latest `master` and create `feature/plan-b-math-distillation`. (Completed by PM)
- [x] Review the execution phases (P0 to P10) in `.agents/plans/B_math_extraction_distillation.md`.
- [x] P0 — Program Setup And Measured Baseline (commit `5a4ea2c`).
- [x] P1 — Docs-First Contract And Migration Specification (commit `ea244d0`).
- [x] **APPROVED — user cleared the Plan B "Mandatory Stop" (P1 contracts
  approved); application code is now authorized from P3 onward.**
- [x] P2 — Failing gold tests and compiler audit oracles. Added
  `docs/specs/failure_atlas/plan_b_compiler_gold.yml` (deterministic +
  human-labeled gold) and `backend/tests/test_plan_b_compiler.py` (9 gold
  structural PASS + 16 `xfail(strict)` schema/support/formula/audit oracles).
  Full suite 732 passed, 26 xfailed; ruff clean. No application code yet.
- [x] P3 — Additive schema and support lifecycle. `db.py` SCHEMA_VERSION 7→8:
  `claim_supports` (§20.2), `compiler_generations` (§20.3), `knowledge_units`
  §20.1 columns (backfill legacy rows `unchecked`/`not_applicable`), tombstone
  CHECK rebuild, and `db_sync` inclusion of both new canonical tables. Added DB
  lifecycle helpers (support upsert/list, support/formula status, retire,
  eligibility, evidence-hash freshness, generation create/publish/discard).
  The 5 §20.1-§20.3/§20.6 SCHEMA oracles flipped to live `test_v8_*` tests; the
  11 behavior oracles correctly stay xfail (P4-P6). Caught + root-fixed a real
  v7→v8 upgrade bug (index on a column not yet added). D2 holdout db.py drift
  fingerprint re-armed to HEAD (user-approved; metric provably unaffected,
  additive change). Full suite 750 passed, 21 xfailed; ruff src/ clean; 0 new
  mypy errors.
- [x] P4 — Claim extraction, minimal support, and stable reconciliation.
  `pipeline/claim_support.py` implements the deterministic structural gate
  (verified|failed|uncertain trichotomy per §26.1), ordered LaTeX token-sequence
  formula check (direction/binding-preserving, contiguous sub-formula aware),
  `normalize_claim`/
  `semantic_hash`, `run_compiler_audit` (freshness + unsupported), and
  `reconcile_source` (retire on deleted cited span). Exposed via
  `pipeline/compile.py`. Un-xfailed 5 behavior oracles (minimal-support,
  wrong-real-span F6, edited-span-stale, source-delete-retire, audit-flags-
  unsupported); added `tests/test_plan_b_support.py` (12 unit tests incl. the
  direction/binding and sub-formula proofs). Suite 768 passed, 16 xfailed; ruff
  src/ clean; 0 new mypy.
  COMPLETE integration: `compile_source_l2` validates with hydrated full span
  text before downstream use; prompt contract is now
  `curator.knowledge_unit_extract@v2` with proposed support roles/formula
  centrality; proposals persist as unchecked and are replaced by the fresh gate
  verdict; ATM/graph/projection re-emission/knowledge-unit search read only
  verified active units; changed/split reconciliation reuses a prior stable id
  only for a verified semantic-hash candidate with whitespace-normalized exact
  statement equality and retires the temporary candidate.
  REVIEW FIX: semantic hashes now only propose reconciliation candidates;
  stable-id reuse requires whitespace-normalized exact statement equality.
  Formula matching now preserves ordered tokens/grouping and admits only exact
  contiguous sub-formulas, preventing exponent/subtraction/fraction reversal.
  Formula-only parse loss routes to P5 as `uncertain`, escaped `\$` is ignored
  as a delimiter, and formula-bearing spans outrank non-formula spans for
  `primary` support. Legacy NULL-hash fallback was explicitly rejected under
  the no-backward-compatibility-shims invariant. F6 textual support failures now
  preserve `formula_status='preserved_in_text'` when the formula structurally
  matches, preventing false P5 recovery. Multi-span textual verdicts now use
  maximum cited-span prose coverage independently from formula-aware primary
  attribution; formula hash input preserves token/formula boundaries; and the
  tokenizer preserves non-alphabetic LaTeX escapes.
- [x] P5 — Selective formula recovery and downstream preservation.
  `pipeline/formula_recovery.py` adds provider-free measured-loss
  classification (`fragmented|image_only|parser_omitted`), additive
  `source_spans.metadata.formula_recovery` candidates, `0.80` +
  validator-trace + exact-claim-formula acceptance gates, hash-verified full
  raw-span revalidation, linked formula evidence, and page-hash invalidation.
  Raw span text/hash remain immutable. Formula-bearing graph input is never
  destructively truncated. Two P5 strict-xfail oracles are now live green
  tests.
- [x] P5/P4 PM REVIEW resolved (user direction "Fix 3 only + reject Fix 4").
  Finding A (TOCTOU/transaction + `preserve_formula` + ambiguous
  `formula_status`) committed. **Fix 3 APPLIED** (real bug): `recover_formula`
  now re-validates against the additive recovered evidence of *every* cited
  span (§26.2), not just the span under recovery — regression
  `test_multi_span_recovery_rehydrates_prior_reviewed_evidence`. **Fix 4
  REJECTED** as a spec violation: its swap would route the F6 wrong-real-span
  case (formula absent + prose fails) to P5 instead of `failed`, contradicting
  §26.1's release-blocking F6 gate — spec-correct behavior pinned by
  `test_f6_with_absent_formula_fails_and_is_not_routed_to_recovery`. **Fixes 1
  & 2 NOT applied**: Fix 1 is behavior-neutral (loss verdict is metadata-only)
  and Fix 2 loosens §26.2's "exactly match" gate beyond spec (current
  exact-token equality fails safe). Full rationale in `B_roadmap_evidence.md`
  "P5/P4 PM Review — Multi-Span Recovery Fix And F6 Gate Defense".
- [x] P6 — Staged atomic publish, full-span hydration, and compiler audit
  (commits `eb59a97`, `e473a05`, `63bfcef`, `52a3b45`). **All four remaining
  Plan B strict-xfail oracles are green** (F10 hydration, idempotent rebuild,
  failed-compile-no-partial-publish, wiki-lint Compiler Integrity surface) plus
  the two Program-1 atlas oracles Plan B owns (F10, F7).
  - **P6a** — `compile.hydrate_span_text`/`hydrate_spans` re-parse the
    registered source and verify by `content_hash` (robust to parser
    normalization / PDF); `evidence.py` source-section + entity items hydrate
    full text, flagging `evidence_status='stale'` when unavailable (never
    silently substituting the preview). `SEARCH_ENGINE_SCHEMA §10.2` reconciled.
  - **P6b** — `run_compiler_audit` extended to the full §20.5 contract
    (dangling/formula-inconsistency/multiple-authoritative/duplicate-candidate +
    broad-fallback recording). **Per user direction, the synthesis.py:110 /
    community_reports.py:211 broad fallbacks are community-report/graph-derived,
    so the audit RECORDS them as Plan-C-assigned and Plan B does NOT modify
    those modules** (Program-1 F6 oracle stays xfail, reassigned to Plan C).
    `reconcile_source` removes the edited source's stale spans (F7, §26.4) via
    `db.delete_source_spans`.
  - **P6c** — `recompile_source` is the staged `GEN-` generation orchestrator
    (publish-gate audit → publish, or discard-on-failure with no partial
    authoritative publish; unchanged rebuild reuses the authoritative
    generation). `compile_source_l2` now publishes via it. D2 holdout `db.py`
    drift fingerprint re-armed (`plan_b_p6_rearm`; additive lifecycle helpers,
    no ranking path, metric provably unaffected).
  - **P6d** — `lint.compiler_integrity` + `run_lint` wiring + non-zero exit on
    release-blocking findings; CLI summary gains a Compiler Integrity line.
- [x] **P6 review** (commits `56c76aa`, `171ea38`): Flaw 1 rejected (false
  positive — validate already precedes reconcile); Flaw 2 fixed (defer
  `generation_id` to after the publish gate — §26.3); Flaw 4 fixed (chunk bulk
  `IN (…)` under SQLITE_MAX_VARIABLE_NUMBER); Flaw 3 (§26.3 read-visibility gap)
  routed to plan-first → **Plan B2**.
- [x] **Plan B2 — Compiler Staging/Authoritative Row Separation** (commits
  `b0dad45`, `aa9cebc`, B2-P1 docs, `b7942ab`, `890468c`). Enforces §26.3:
  visibility gated at write/materialization time. A 2nd plan review corrected
  three fatal flaws (PK paradox → publish-time reconcile; graph leak → graph
  upsert after the gate; zero-unit guard removed). **All 6 B2 oracles green.**
  - **B2-P3** — `list_serving_units` (authoritative ∧ verified ∧ not-retired) /
    `list_generation_units`; one-time `GEN-mig-<source_id>` backfill of legacy
    NULL-generation units in `init_db` (data-only, no SCHEMA_VERSION bump).
  - **B2-P4** — `compile_source_l2` copy-on-stage: stage extracted units in a
    fresh generation, validate + gate before any served write, then publish
    atomically (retire prior-gen units, flip authoritative) and emit ATM + graph
    + search ONLY from the authoritative served set; a failed gate/error discards
    the staged units with the prior generation untouched (no orphan graph).
    `materializer` + `reemit_projections` read `list_serving_units`. Graph stays
    span-based (generation-scoping it is Plan C, per user direction).

## Verification

- `uv run --directory backend pytest -q` → **817 passed, 8 xfailed** (P6 +
  P6-review + Plan B2 complete). The 8 remaining xfails are Program-1 F6/F8/F9
  (→ Plan C) and F3/F4/F5/F11/F12 (→ Program 3). **Zero Plan B / B2 xfails
  remain.**
- `uv run --directory backend ruff check src/` → clean.
- `uv run --directory backend mypy src/` → 72 pre-existing errors, 0 introduced
  (compile.py / claim_support.py / db.py / materializer.py / lint.py clean; the
  cli.py errors predate Plan B).
- `VAULT_ROOT=$REPO/testbed wiki status` → gaussian_splatting testbed healthy
  (3 sources, L1 done, L2-L4 pending; pre-existing "vault schema v0 → v1"
  warning predates Plan B). `wiki lint` → Compiler Integrity clean, exit 0.
- `npx vitest run` (plugin) → 44 files, 361 tests passed (no plugin change).
- Testbed DB migration to v8 + provider-backed extraction happen at P7.

## Critical Context And Blockers

- No active implementation blocker; the P1 mandatory stop was approved.
- Frozen P1 design points the user should review: `claim_supports` roles
  (`primary|contextual|formula`), support statuses
  (`unchecked|verified|failed|stale`), `formula_status` enum,
  `compiler_generations` (`GEN-`) staged-publish table, recovery candidates
  in `source_spans.metadata.formula_recovery` (no new table by default),
  compiler audit surfaced through `wiki lint` (no new CLI command, no plugin
  /MCP schema changes).
- Environment note: stray `backend/.venv` removed and root `.venv` recreated
  (stale shebangs from the old `llm_wiki` repo path were silently falling
  back to Anaconda). Use `uv run --directory backend ...` from the repo root.
- `wiki status` with a relative `VAULT_ROOT` resolves against `backend/` when
  run via `uv run --directory backend`; use an absolute path.

## Immediate Next Action

**P0–P6, the P6 review, Plan B2 (+ its two review rounds), and P7 are all
complete and committed.** Backend suite green (824 passed, 8 xfailed), ruff
clean, 0 introduced mypy, plugin vitest green. The remaining xfails are Plan-C
(F6/F8/F9) and Program-3 (F3/F4/F5/F11/F12) targets, not Plan B's. B2 folds into
the v0.8.0 release; both plan files
(`.agents/plans/B_math_extraction_distillation.md`,
`.agents/plans/B2_compiler_staging_separation.md`) are deleted at the P10 step.

- [x] **P7 — Testbed + end-to-end compiler audit (provider-backed).** §26.6
  migration rehearsal on a disposable backup copy passed all criteria; live
  testbed migrated to v8 (backed up first). A real **Antigravity (`agy`)**
  `wiki build` validated the B2 copy-on-stage path E2E: source 1's graph LLM
  returned non-conforming JSON → **atomic discard, 0 partial state**; sources 2,3
  published authoritative; source 3's authoritative gen holds non-verified
  stored-not-served units; **0 served units in a non-auth gen** (no leak), one
  authoritative per source, 0 NULL-gen units; `wiki lint` → 11 release-blocking
  F6 findings + **exit 1**; ATM pages only for served units; **no source/
  reference file edited**. Only gap: source 1's model-output graph-JSON failure
  (not a B2 defect). Full record in `B_roadmap_evidence.md` "P7".

**Next: P8 — Sequential role reviews** (coder_engineer, peer_reviewer,
schema_guardian, source_pair_analyst, qa_runner, docs_sync_manager,
legacy_sweeper). Then P9 (full local CI incl. plugin vitest) and P10 (version
bump to v0.8.0 + CHANGELOG + delete both plan files + release commit + PR).

The P4 support-validation mechanism is SETTLED (SYSTEM_BEHAVIOR §26.1; rationale
in `B_roadmap_evidence.md` "P4 Design Decision"): a deterministic STRUCTURAL
gate (verified|failed|uncertain trichotomy) primary, calibrated model secondary
for `uncertain` only. Formula check = ordered normalized token sequence over
inline `$...$` AND display `$$...$$` (preserves direction/binding; accepts only
contiguous sub-formulas; no AST/CAS); text check = salient entity/term intersection
above threshold (zero overlap → `failed`, the F6 gate). Validate on hydrated
FULL span text, never the preview. Do NOT lookup the gold YAML at runtime
(overfitting ban); it is the test-time release oracle only.

### Update (2026-06-13)

The `B2_compiler_staging_separation.md` plan (addressing Flaw 3) is structurally sound and mathematically safe. 

**Next Action**:
Await final User Approval for the `B2_compiler_staging_separation.md` plan. Once approved, proceed with implementation starting from P1.

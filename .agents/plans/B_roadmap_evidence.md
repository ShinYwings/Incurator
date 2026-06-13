# Plan B Evidence Ledger (Coding-Time)

Date: 2026-06-13
Branch: `feature/plan-b-math-distillation`
Rollback anchor: `688c6d0c478104494bf3cca9841a58c5f535ca6c`
(= merged Program 1 `master` `5a3932cbdcd84055e3b8d5bc03b959c384e465be`
plus two PM workflow chore commits)

This is the coding-time ledger required by Plan B
(`.agents/plans/B_math_extraction_distillation.md` — "Evidence Ledger Refresh
Deliverable"). The Arena ledger at
`.agents/plans/math_extraction_distillation_arena/04_evidence_ledger.md` is a
planning snapshot only.

## Current Repository And Schema Reality

- Program 1 is fully merged: D1 (`v0.6.0`), SQLite leak hotfix (`v0.6.1`),
  Plan E (PR #26), D2 (`v0.7.0`, PR #28). Branch is created from the merged
  `master` at `5a3932c`.
- Backend/plugin version at baseline: `0.7.0` (`backend/pyproject.toml`,
  `plugin/package.json`, `plugin/manifest.json` agree).
- `state.sqlite` schema version: `7` (from the `schema_version` table;
  `PRAGMA user_version` is unused and reads 0).
- `wiki status` reports a pre-existing, non-blocking warning:
  "Vault schema v0 → backend expects v1. Run wiki migrate to upgrade."
  This predates Plan B and is not introduced by this branch.
- `source_spans` deduplicates by `(source_id, content_hash)`, stores a
  200-char `text_preview` (`_PREVIEW_CHARS = 200`), and accepts metadata.
  Confirmed unchanged from the planning inspection.
- `knowledge_units` has no `semantic_hash`, `support_status`,
  `formula_status`, or `retired_at` columns, and there is no
  `claim_supports` table — the Plan B candidate schema is entirely additive
  from this baseline.
- No stale-dependency invalidation API exists in `db.py` (F7 boundary
  evidence re-confirmed by the passing repro suite at this SHA).

## Baseline And Rollback Evidence

- Active testbed scenario: `gaussian_splatting` (confirmed from the
  initialized `testbed/` workspace: 2D Gaussian Splatting + EWA splatting
  papers in `03_Notes/Papers` and `04_Resources/Zotero`, workspace
  `01_Workspaces/Gaussian Splatting Geometry Lab/`). The historical
  `complex_math_backprop` scenario is NOT present under `tests/scenarios/`;
  per Plan P2/P7 it will be rewritten as the math-specific scenario rather
  than assumed active.
- Providers/models at baseline (`wiki status`):
  - Primary LLM: Antigravity CLI (`gemini-3.5-flash`), fallback none.
  - Embedding: `llama-cpp::qwen3-embedding-0.6b`.
  - Search engine: `native-0.7.0` in-DB FTS5 + vector, reranking on.
- Testbed DB SHA-256 before Plan B:
  `4bb46326faf8512f88b51c7a35bbe3d31ac36fafbf1cf887759db1784a6109cc`
  (unchanged since the D2 pre-observatory backup).
- Testbed DB backup: `.agents/backups/b-pre-implementation-state.sqlite`
  (gitignored), SHA-256 identical to the live DB; restoration verified —
  `PRAGMA integrity_check` = ok on the backup copy.
- Testbed DB baseline row counts: 3 `sources`, 212 `source_spans`,
  0 `knowledge_units`, 0 `synthesis_nodes`. Pipeline state: L1 done (3/3),
  L2/L3/L4 pending (0/3 each).
- Testbed `curate.yml` SHA-256
  (`01_Workspaces/Gaussian Splatting Geometry Lab/curate.yml`):
  `a45b5ef13bff1d335ff1d95a95e1df9d6e34d338bd7aef6644e6e17633ed672f`.
- Failure Atlas fixture corpus SHA-256:
  `35301871bdd1e8e676d63c032e7c566d863a9760f94d1c00e5de8217e364603b`.
- Failure Atlas qrels SHA-256:
  `e3b254054779595aa4157df82db1c885356e3763f35430be0b23bb187c35c6a0`.
- Failure Atlas support labels SHA-256:
  `89f7842824e381931735583cb1dc28b79d471ea425df88cc9d6e7cd63c4478d5`.
- DB schema fingerprint (SHA-256 over ordered `sqlite_master` DDL):
  `32de7dcfcb87e23a0e2c47985c9fbcbf05e6b30012f10da198e8ba594a9a0842`.

## P0 Measured Baseline (Program 1 Suites At This SHA)

All five Program 1 failure-atlas suites pass at the rollback anchor:

```
uv run --directory backend pytest tests/test_failure_atlas_repro.py \
  tests/test_failure_atlas_contract.py tests/test_failure_atlas_experiments.py \
  tests/test_failure_atlas_d2.py tests/test_failure_atlas_eval.py -q
135 passed, 10 xfailed
```

The 10 strict-xfail oracles are the frozen Program 1 targets. Plan B owns
turning F6, F7, and F10 oracles green; F8/F9 are Program 2 cases owned by
Plan C (graph), and F3/F4/F5/F11/F12 are Program 3.

### Failure Boundary Classification (P0 Deliverable)

| Concern (Plan B P0) | Atlas case / evidence | Boundary | Status |
|---|---|---|---|
| Formula loss (distillation) | Plan E Wave D FR01: distillation drops a formula present in authoritative extraction; FR05 holdout: distillation adds nothing absent from extraction | downstream distillation prompt path (no formula-preservation check exists) | **Reproduced** (frozen Wave D result); adopted contract: formula-preserving distillation |
| Formula loss (parser/L1) | L1 preserves `$$...$$` only when parser output contains them; no per-class loss verdicts (`fragmented`/`image_only`/`parser_omitted`) measured yet on the current corpus | `parsers/*` → L1 span path | **Scheduled** — P2 gold fixtures + P5 loss-boundary classifier; recovery work stays blocked until these verdicts are measured (Plan stop condition) |
| Wrong-real-span support | F6: `synthesis.py:110` `item_spans = list(item.source_span_ids) or span_ids`; `curator.synthesis_write` validator chain omits `requires_source_spans` | synthesis persistence; valid span id treated as proof of support | **Reproduced** (deterministic, xfail oracle `test_f6_oracle_synthesis_spans_match_declared_support`) |
| Unchanged rebuild | F7 partial pass: unchanged re-store IS id-stable at L1; search upsert row-idempotent. L2+ rebuild identity undefined (`upsert_knowledge_unit()` creates new ids by default) | `db.upsert_knowledge_unit`, compile generation identity | **Reproduced at L1 / Scheduled at L2+** — provider-mode portion documented as blocked in F7 notes |
| Edit (stale rows) | F7: edited content creates new span rows, old rows linger; stale-citing synthesis untouched; no invalidation API | `source_spans.store_source_spans`, missing dependency-closure API | **Reproduced** (deterministic, xfail oracle `test_f7_oracle_source_edit_reconciles_stale_spans`) |
| Delete/split reconciliation | No Program 1 fixture exercises source delete or split | same reconciliation boundary as F7 | **Scheduled** — P2 gold fixtures (`edit/delete/split`), P4 reconciliation |
| Failed compile (partial publish) | `compile_source_l2()` makes persistent writes across multiple stages before all stages validate (planning evidence, re-confirmed in code at this SHA); no atomicity test exists | staged-generation publish boundary | **Accepted as real / Scheduled** — P6 failure injection at every publish boundary |
| Evidence truncation | F10: `_PREVIEW_CHARS = 200` is the only stored span text; evidence packs present the preview as span evidence | `source_spans.SourceSpan.text_preview`, `evidence.py` pack items | **Reproduced** (deterministic, xfail oracle `test_f10_oracle_full_span_text_retrievable`) |

Every P0 concern is therefore reproduced, accepted, or explicitly scheduled;
none is disproven. No recovery (VLM) work is approved yet — the P5 gate
requires measured per-class loss verdicts first.

## Current Dirty Worktree

- `.agents/RELAY.md` — modified by the PM (Plan B kickoff state), uncommitted.
  Preserved; Plan B appends progress to it rather than reverting.
- No other tracked files were modified at ledger creation time.

## Environment Repairs Performed During P0 (No Code Behavior Change)

- Removed a stray `backend/.venv` (policy: the backend venv lives at the repo
  root only). It was shadowing the root venv for `uv run` script resolution.
- Recreated the root `.venv`: its console-script shebangs still pointed at the
  pre-rename repo path (`~/Workspace/llm_wiki/...`), which silently fell back
  to the Anaconda toolchain. After `rm -rf .venv && uv sync --directory
  backend --extra dev --extra mcp`, `uv run --directory backend pytest`
  resolves to `<repo>/.venv` correctly.

## Migration Rehearsal Status

- The Plan B additive migration does not exist yet (P3 scope). Rehearsal on a
  disposable DB copy is REQUIRED before the migration touches the testbed DB,
  using `.agents/backups/b-pre-implementation-state.sqlite` as the rehearsal
  input. Acceptance criteria are frozen in the P1 contract documents.
- Clean rebuild from source truth is preserved: testbed sources are intact
  under `03_Notes/` and `04_Resources/` (read-only), and L2+ state is empty
  at baseline, so a full recompile is the trivial recovery path.

## P2 — Failing Gold Tests And Compiler Audit Oracles (Completed)

User approval of the P1 contracts was given (the Plan B "Mandatory Stop" is
cleared); P2 adds tests and labeled fixtures only — no application/behavior
code, so no version bump (that is P10).

### Deliverables

- `docs/specs/failure_atlas/plan_b_compiler_gold.yml` — deterministic +
  human-labeled gold oracle fixture (Arena decision 10). Covers: 10 synthetic
  L1 spans (central/incidental/equation/figure/long-tail), 4 support cases
  (single-span, multi-span primary+contextual, F6 wrong-real-span, contradiction
  across source revisions), 8 formula cases (preserved_in_text, linked_evidence,
  omitted_incidental + reason code, missing on image-only loss, below-threshold
  uncertain recovery, all three loss verdicts `fragmented`/`image_only`/
  `parser_omitted`, and the F10 long formula tail), 4 reconciliation cases
  (unchanged/edit/delete/split with expected closure), and 2 staged-publish
  failure cases. All enums match SCHEMA §20 exactly.
- `backend/tests/test_plan_b_compiler.py` — 9 `test_gold_*` structural tests
  (PASS now: fixture integrity + enum conformance) and 16
  `test_oracle_* xfail(strict=True)` contract oracles spanning the v8 schema
  (§20.1-§20.3, §20.6), minimal-support lifecycle (§26.1 / F6), formula
  lifecycle + selective recovery (§26.2, §20.4), full-span hydration
  (SEARCH §10.2 / F10), staged atomic publish + idempotent rebuild (§26.3 /
  F7), edit/delete/split reconciliation (§26.4), and the read-only compiler
  audit traversing active claims to exact support (§20.5 / §26.5), including a
  `wiki lint` Compiler Integrity surface oracle.

### Oracle Mechanism

Schema oracles assert name-stable frozen-spec facts (table/column/version), so
they are the reliable XPASS triggers when P3 ships the additive migration.
Behavior oracles assert observable DB/audit outcomes of the gold cases and
resolve the Plan B entry point lazily (`_resolve(...)` over `db` + the compile
pipeline), so this file does not pre-guess internal symbol names; P3-P6 point
each oracle at the real API when turning it green. No not-yet-implemented
symbol is imported at module top — collection never breaks.

### `complex_math_backprop` Scope Note (P2 honest finding)

There is NO `complex_math_backprop` pytest to "rewrite": that scenario is
absent from `tests/scenarios/` (confirmed in this ledger's baseline). The
nearest active math scenario is `resnet_neural_ode` (discrete residual blocks
↔ continuous ODE dynamics). Per Root-Cause-Over-Workarounds, no fake test was
fabricated to satisfy the checklist item — the math-specific deterministic
cases were folded into `plan_b_compiler_gold.yml`, and the testbed scenario
rewrite against DB-native L1-L4 + Reference Mode remains P7 scope.

### Verification

```
uv run --directory backend pytest tests/test_plan_b_compiler.py -q
  → 9 passed, 16 xfailed   (no xpass, no collection error)
uv run --directory backend ruff check tests/test_plan_b_compiler.py
  → All checks passed!
uv run --directory backend pytest -q
  → 732 passed, 26 xfailed   (baseline 723/10 + 9 gold passes + 16 oracles;
     all 10 Program 1 strict-xfail oracles preserved)
```

Expected red→green gate confirmed: new behavior oracles fail (xfail) for the
intended reasons; unchanged legacy tests remain green.

## P3 — Additive Schema And Support Lifecycle (Completed)

User approval at the Mandatory Stop authorized application code; P3 ships the
v8 additive migration and the SCHEMA §20 DB lifecycle helpers. No version bump
(P10).

### Implementation

- `backend/src/curator/db.py`: `SCHEMA_VERSION` 7 → 8. `SCHEMA_SQL` gains the
  `knowledge_units` §20.1 additive columns (`semantic_hash`, `support_status`
  default `unchecked`, `support_reason`, `formula_status` default
  `not_applicable`, `retired_at`, `generation_id`), the `claim_supports` (§20.2)
  and `compiler_generations` (§20.3) tables + indexes, and the extended
  `deleted_records` CHECK (admits the two new canonical tables). New
  `_migrate_v8_compiler_integrity()` upgrades existing v7 DBs idempotently:
  `_add_column_if_missing` backfills every legacy `knowledge_units` row as
  `support_status='unchecked'` / `formula_status='not_applicable'` (nothing
  silently verified), `CREATE TABLE IF NOT EXISTS` adds the two tables, and the
  `deleted_records` CHECK is rebuilt (table-swap) when it predates Plan B.
- Lifecycle helpers (storage mechanics only; validation logic is P4-P6):
  `upsert_claim_support`, `list_claim_supports`, `set_unit_support_status`
  (rejects empty reason for failed/stale), `set_unit_formula_status`,
  `retire_knowledge_unit`, `list_eligible_knowledge_units` (retired_at IS NULL
  AND support_status='verified' — the §20.1 eligibility rule; excludes legacy
  `unchecked`), `refresh_support_freshness` (§26.1 evidence-hash re-check →
  stale), `create_compiler_generation` / `get_authoritative_generation` /
  `publish_compiler_generation` (enforces one authoritative per source scope) /
  `discard_compiler_generation`.
- `backend/src/curator/db_sync.py`: `claim_supports` (composite PK, always-upsert)
  and `compiler_generations` (PK `id`, always-upsert — no `updated_at` column)
  added to `SYNC_TABLES`, `_UPDATED_AT_COL`, `_PK_COL`, so both are canonical
  synced tables with tombstone support (SCHEMA §20.2/§20.3).

### Real upgrade bug caught by the migration test

The two new `knowledge_units` indexes were initially placed in `SCHEMA_SQL` as
bare `CREATE INDEX` statements. On a pre-existing v7 DB, `executescript(SCHEMA_SQL)`
runs BEFORE `_apply_migrations`, and `CREATE TABLE IF NOT EXISTS knowledge_units`
does not add columns to the existing table — so indexing `support_status`/
`generation_id` failed with "no such column" on every real v7→v8 upgrade. Fixed
at the root: the support/generation indexes are created only in
`_apply_migrations` (after the columns are added), valid for both fresh and
migrated DBs.

### Oracle status changes (red → green, deliberate un-xfail)

The five §20.1-§20.3/§20.6 SCHEMA oracles XPASS under the migration and were
converted from `xfail(strict)` oracles to live `test_v8_*` regression tests in
`tests/test_plan_b_compiler.py`. The 11 behavior oracles (support validation,
formula lifecycle, audit, reconciliation, atomic publish) correctly remain
xfail — they are P4-P6 targets.

### New P3 tests

`backend/tests/test_plan_b_migration.py` — §26.6 acceptance criteria on a
synthetic v7 DB (CI-safe; the real backup rehearsal is a P7/manual step):
additive upgrade + conservative backfill, idempotent re-migration, deterministic
schema fingerprint, fresh-vs-migrated column-set equivalence, export/import
round-trip of the new tables, backup/restore integrity; plus unit tests for
every lifecycle helper (claim-support upsert/list/enum-guards, eligibility
exclusion of unchecked/retired, freshness→stale, generation publish/discard
invariants).

### Version-pinned test updates (consequence of the SCHEMA_VERSION bump)

- `tests/test_db_schema.py::test_schema_version_is_7` → `_is_8`.
- `tests/test_db_sync.py::test_schema_version_bumped_to_7` → `_8`; export header
  assertion 7 → 8.
- `docs/specs/curator_schema/SCHEMA.md` §11 header + version-history extended to
  `SCHEMA_VERSION = 8`.
- The `test_failure_atlas_d2.py` frozen-holdout values (`db_schema_version: 7`,
  `package_version: 0.7.0`) are HISTORICAL records of the D2 run and are NOT
  tied to `db.SCHEMA_VERSION`; left unchanged. `test_research_spikes_wave_b.py`'s
  inline `schema_version 7` is arbitrary read-only fixture data; left unchanged.

### D2 holdout drift fingerprint re-armed (USER-APPROVED governance call)

The D2 holdout test pins `backend/src/curator/db.py` by SHA-256. Plan B's
additive v8 change necessarily alters that hash; the single-consumption harness
(`run_count=3`, max) cannot regenerate the result. The user chose **re-arm the
fingerprint to HEAD**: `docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml`'s
`evaluated_code.file_sha256[db.py]` updated to the new hash, with an inline
`plan_b_rearm` provenance note recording the prior hash and the rationale (the
change touches no retrieval/ranking/projection/`materialize_chunks` path the
lexical FTS5/BM25 holdout exercises, so the frozen Q06 metric is provably
unaffected; git history + `git_sha` preserve the original provenance).

### Verification

```
uv run --directory backend pytest tests/test_plan_b_migration.py \
  tests/test_plan_b_compiler.py -q  → 27 passed, 11 xfailed
uv run --directory backend pytest -q  → full suite green (see RELAY)
uv run --directory backend ruff check src/ tests/  → clean
uv run --directory backend mypy src/  → 73 pre-existing errors, 0 introduced by
  P3 (verified by stash-compare: identical count with and without the db.py /
  db_sync.py changes)
```

## P4 Design Decision — Support-Validation Mechanism (settled, pre-code)

The P4 support-validation fork (content-entailment vs gold-fixture lookup vs
structural checks) is settled as a HYBRID: a deterministic structural gate
primary, calibrated model secondary. Frozen into SYSTEM_BEHAVIOR §26.1. Origin:
user research note `p4_support_validation_research.md`, fact-checked against the
gold fixtures + oracles. Adopted points and the four corrections applied:

- ADOPT: structural-primary + model-secondary; ban gold-fixture lookup from
  runtime (overfits — fixtures are the test-time release oracle only); reject
  pure NLI/embedding entailment for formulas (`a^2+b^2` vs `a^2-b^2` hole).
- CORRECTION 1: parse inline `$...$` AND display `$$...$$` LaTeX — every gold
  formula case uses INLINE `$...$`; a `$$`-only parser misses them all.
- CORRECTION 2 (superseded by P4 review fix): the initial implementation used
  a normalized symbol/operator token multiset. Reviewer counterexamples proved
  the flat sort erased operation direction/binding (`a^b` vs `b^a`, `a-b` vs
  `b-a`, `\frac{a}{b}` vs `\frac{b}{a}`), so it is no longer accepted.
- CORRECTION 3: the gate yields a TRICHOTOMY `verified | failed | uncertain`,
  not fail-only. The SUP01 oracle calls `validate(db, unit_id)` with NO model
  and expects `verified`, so clear matches must verify deterministically; only
  `uncertain` (ambiguous paraphrase) escalates to the model, and stays
  `unchecked` when no model is available.
- CORRECTION 4: validate on hydrated FULL span text, not the 200-char
  `text_preview` (preview truncation = F10; production correctness couples to
  the P6 full-span hydration). Short gold spans make preview==full, so the P4
  oracles pass on preview alone.

Target oracles this turns green (un-xfail in the P4 change):
`test_oracle_minimal_support_yields_verified_primary_row` (SUP01, deterministic
verify), `test_oracle_wrong_real_span_marked_failed` (SUP03, deterministic
fail via zero entity intersection), and the reconciliation oracle
`test_oracle_source_delete_retires_dependent_claim` (REC03). The
`test_oracle_edited_span_marks_support_stale` oracle needs a
`compiler_audit`/`run_compiler_audit` entry point wiring P3's
`refresh_support_freshness`.

### Advanced formula-verification ideas — evaluated (opinion only, not adopted now)

Considered three rigor escalations; P4 uses deterministic ordered token
subsequence matching. Recorded so they are not re-litigated:

- SymPy symbolic equivalence (`A - B = 0`): **benchmark-later**, not the P4
  primary. Stronger on pure algebraic equivalence, but LaTeX→SymPy parsing is
  fragile on real notation (the gold formulas alone include a transpose
  `x^{T}`, a gradient `\nabla_W L`, an outer product, an update rule
  `\leftarrow` that is not an equation, and a norm `\lVert J \rVert`), and the
  case it uniquely catches (equivalent restatement) is rare in distillation and
  already handled by the trichotomy routing a mismatch to `uncertain`→model.
  Adopt only with a measured win + acceptable real-corpus parse rate, as a
  stronger `verified` signal when both sides parse to compatible types.
- Lean/Rocq formal verification: **rejected**. Verifies mathematical TRUTH, not
  evidence GROUNDING (Plan B's actual goal); most KB units are not formalizable;
  unbounded per-claim formalization cost. Hard non-goal.
- Fine-grained PRM / graph-of-verification: **deferred**. Major architecture
  change that lands on Plan B non-goals (hierarchy/relations = Plan C) and
  reintroduces model dependence (a PRM is a trained model).

### Parse-fidelity vs P4 grounding (finding)

Verified the parsers: Markdown `.md` is faithful LaTeX passthrough
(`parsers/text.py`; `normalize_text` only collapses whitespace, which the gate
also does), so the gate is solid for notes. PDFs are best-effort
(`pymupdf4llm` + a math-ish raw-text fallback) and cannot recover LaTeX from a
rendered text layer — a fundamental limit, not a bug; a VLM routing placeholder
already exists at `parsers/pdf.py`. P4 does NOT block on parse fidelity because
it is a RELATIVE grounding check (claim vs the same L1 span it came from), and
on lossy sources it degrades to `uncertain` (never a wrong verify). The
source-fidelity gap (L1 span vs original paper) is closed by P5, now explicitly
extended to cover the `fragmented`/garbled-but-present case and the P4→P5
`uncertain` routing (plan P5, SCHEMA §20.4, SYSTEM_BEHAVIOR §26.2 updated).

## P4 — Claim Support Validation Core (Completed; integration remaining)

`backend/src/curator/pipeline/claim_support.py` implements the §26.1 structural
gate deterministically (no LLM, no gold-fixture lookup):

- `_formula_tokens` + `_is_formula_subsequence`: normalized ordered LaTeX token
  sequence over inline `$...$` and display `$$...$$`. Spacing macros are
  ignored, grouping braces and operation order are preserved, and a faithful
  contiguous sub-formula is accepted. Proven by direction/binding and
  sub-formula regression tests.
- `_content_terms` (LaTeX stripped, len≥3, stopwords removed) +
  `_term_coverage`; `normalize_claim` / `semantic_hash` (deterministic
  reconciliation fingerprint).
- `validate_claim_support` trichotomy: `failed` (coverage < 0.25 → F6
  wrong-real-span, reason contains "does not minimally support"), `uncertain`
  (right topic but formula absent/altered → `formula_status='uncertain'`,
  routed to P5; or ambiguous text → model), `verified` (coverage ≥ 0.5 → primary
  support on the best span, contextual on the rest, `formula_status=
  'preserved_in_text'` when the formula matches). Writes `claim_supports` +
  sets unit `support_status`/`formula_status`/`semantic_hash`.
- `run_compiler_audit` (read-only: freshness re-check via P3
  `refresh_support_freshness` + active-unverified reporting) and
  `reconcile_source` (retire active units whose cited spans were deleted).
- Exposed via `pipeline/compile.py` so the oracle resolver finds them.

Un-xfailed 5 behavior oracles (minimal-support, wrong-real-span, edited-span-
stale, source-delete-retire, audit-flags-unsupported). Added
`tests/test_plan_b_support.py` (12 unit tests). Full suite 768 passed, 16
xfailed; ruff src/ clean; mypy 73 (0 new). The 6 remaining Plan B oracles are
P5 (central-formula preserved/recovery) and P6 (F10 hydration, staged publish,
wiki lint surface).

## P4 — Compile Integration, Eligibility, And Stable Reconciliation (Completed)

- `compile_source_l2` now validates every extracted unit against hydrated full
  span text before any ATM projection or graph input is produced.
- `curator.knowledge_unit_extract@v2` declares minimal support roles
  (`primary | contextual | formula`) and formula centrality. Extraction stores
  the proposed support rows as `unchecked`; deterministic validation replaces
  prior/proposed rows with one fresh verdict, preventing stale verified support
  from surviving re-validation.
- ATM projection, graph input, projection re-emission, and knowledge-unit search
  materialization now use only active `support_status='verified'` units.
- `reconcile_source` accepts the current span set and newly extracted candidates.
  A verified candidate with the same semantic hash and normalized statement may
  revalidate the prior stable id after an edit/split; materially different
  claims retire instead. Candidate ids are tombstoned after stable-id reuse.
- Added compile-path, unsupported-downstream-exclusion, prompt-v2, proposal
  persistence, re-validation replacement, search/projection eligibility, and
  split reconciliation coverage.

P4 final verification:

- `uv run --directory backend pytest -q` → 772 passed, 16 xfailed.
- `uv run --directory backend ruff check src/` → clean.
- Changed P4 files targeted by mypy are clean except the pre-existing
  `knowledge_units.py:79` missing annotation already present at the rollback
  anchor; full mypy remains at the known 73 pre-existing errors.

Next phase: P5 selective formula recovery and downstream formula preservation.

## P4 Review Fix — Directionality And Formula Binding

An in-flight review found two release-blocking false-merge/false-verification
cases in the initial P4 implementation:

- `semantic_hash` and `normalize_claim` both use a lossy term-set
  normalization, so reversed claims such as `A causes B` / `B causes A` can
  collide. Reconciliation now uses the hash only to propose a candidate and
  requires whitespace-normalized exact statement equality before stable-id
  reuse.
- Flat sorted formula tokens erased operation direction and grouping. Formula
  matching now preserves ordered tokens and grouping braces. A claim formula
  verifies only when it is an exact contiguous token subsequence of a cited
  span formula, allowing faithful sub-formulas without accepting exponent,
  subtraction, or fraction reversal.

The reviewer's raw-string substring suggestion was not adopted because it can
match inside larger LaTeX commands/tokens. Ordered token subsequence matching
retains token boundaries.

Review-fix verification:

- `uv run --directory backend pytest -q` → 775 passed, 16 xfailed.
- `uv run --directory backend ruff check src/` → clean.
- `uv run --directory backend mypy src/curator/pipeline/claim_support.py` →
  clean.

## P4 Review Fix — Formula-Only Parse Loss And Escaped Dollars

A second in-flight review found two release-blocking edge cases:

- Formula-only claims have no prose terms, so their text coverage is `0.0`.
  The initial verdict order hard-failed a missing/altered formula before it
  could route to P5. Textual low-overlap failure now applies only when salient
  prose exists. Formula-only exact matches verify; formula-only mismatches stay
  `uncertain`; claims with neither salient prose nor a formula fail explicitly.
- `_LATEX_RE` treated escaped literal/currency dollars (`\$`) as delimiters.
  Unescaped negative-lookbehind delimiters now parse real inline/display math
  without consuming escaped dollar text.

Added regression coverage for formula-only parse loss, empty/garbage claims,
and escaped-dollar text mixed with a real inline formula.

Second review-fix verification:

- `uv run --directory backend pytest -q` → 778 passed, 16 xfailed.
- `uv run --directory backend ruff check src/` → clean.
- `uv run --directory backend mypy src/curator/pipeline/claim_support.py` →
  clean.

## P4 Review Fix — Primary Formula Span

A third in-flight review found a support-attribution edge:

- Formula-only multi-span claims gave every span prose coverage `0.0`, so the
  first cited span became `primary` even when another span contained the
  matching formula. Primary selection now ranks spans by
  `(matched claim formulas, prose term coverage)`.

The review also proposed dynamically computing missing legacy semantic hashes.
That proposal was rejected by user direction and the repository's no-backward-
compatibility-shims invariant. Unvalidated legacy NULL-hash rows are not
silently reused.

Added regression coverage proving the formula-bearing span becomes primary.

Third review-fix verification:

- `uv run --directory backend pytest -q` → 779 passed, 16 xfailed.
- `uv run --directory backend ruff check src/` → clean.
- `uv run --directory backend mypy src/curator/pipeline/claim_support.py` →
  clean.

## P4 Review Fix — Text Failure Does Not Erase Formula Preservation

A fourth in-flight review found an inconsistent cross-axis status: a
formula-bearing claim with hallucinated/unsupported prose correctly failed F6
text grounding, but the same branch marked an exactly matched formula
`missing`. The text-failure branch now preserves `formula_status=
'preserved_in_text'` when structural formula matching succeeds. This keeps the
failed support verdict without falsely routing an existing formula to P5.

Added regression coverage for `support_status='failed'` together with
`formula_status='preserved_in_text'`.

Fourth review-fix verification:

- `uv run --directory backend pytest -q` → 780 passed, 16 xfailed.
- `uv run --directory backend ruff check src/` → clean.
- `uv run --directory backend mypy src/curator/pipeline/claim_support.py` →
  clean.

## P4 Review Fix — Decoupled Coverage And Formula Token Fidelity

A fifth in-flight review found three independent structural issues:

- Multi-span verdicts reused the prose coverage of the formula-ranked
  `primary` span. The gate now evaluates text thresholds against the maximum
  prose coverage across every cited span while retaining formula-aware primary
  attribution.
- Formula tokens were concatenated without a delimiter in the semantic-hash
  input. Formula token arrays are now structurally serialized, preventing both
  token collisions such as `\alpha b` / `\alphab` and formula-boundary
  collisions such as `$a$ $b$` / `$a b$`.
- The formula tokenizer silently dropped backslashes before non-alphabetic
  escaped characters. A fallback escape token now preserves distinctions such
  as `\{x\}` versus `{x}` and matrix row separators (`\\`).

Added regression coverage for split text/formula support, semantic-hash token
boundaries, and non-alphabetic LaTeX escapes.

Fifth review-fix verification:

- `uv run --directory backend pytest -q` → 782 passed, 16 xfailed.
- `uv run --directory backend ruff check src/ tests/test_plan_b_support.py` →
  clean.
- `uv run --directory backend mypy src/curator/pipeline/claim_support.py` →
  clean.

## P5 Selective Formula Recovery And Downstream Preservation

Implemented the provider-free P5 boundary without whole-corpus recovery:

- `classify_formula_loss` emits `fragmented`, `parser_omitted`, or
  `image_only` only from measured parser/raw/extraction/rendered-region
  evidence; an expected formula alone schedules nothing.
- `recover_formula` accepts only P4 `formula_status='uncertain'` claims and
  appends full-lineage candidates to `source_spans.metadata.formula_recovery`
  without changing raw `text_preview` or `content_hash`.
- A candidate becomes reviewed/served only at confidence `>= 0.80`, with a
  validator trace, an exact ordered-token match to an owning-claim formula,
  and hash-verified hydrated full raw-span text for every cited span. It then
  re-runs claim support before creating linked formula evidence.
- Page-hash drift rejects only stale page candidates and marks previously
  linked formula support stale. Formula-bearing graph statements are no longer
  destructively truncated.

P5 verification:

- `uv run --directory backend pytest -q` → 790 passed, 14 xfailed.
- Focused P5/P4/compiler/entity/spec suite → 65 passed, 4 xfailed.
- `uv run --directory backend ruff check src/ ...` → clean.
- `uv run --directory backend mypy` on P5/graph/compile targets → clean.
- `VAULT_ROOT=$REPO/testbed wiki status` → healthy preflight; L1 complete,
  L2-L4 pending, existing schema-v0 migration warning unchanged.

## P5/P4 PM Review — Multi-Span Recovery Fix And F6 Gate Defense

The 2026-06-13 PM review (RELAY.md) queued four control-flow fixes plus
Finding A (TOCTOU) and Finding B (regression tests). Each was verified against
the authoritative spec (`SYSTEM_BEHAVIOR.md §26.1/§26.2`) and the gold oracle
(`plan_b_compiler_gold.yml`) before any code change. User direction (this
session): **"Fix 3 only + reject Fix 4."** Outcome:

- **Finding A — COMMITTED.** `recover_formula` and
  `invalidate_formula_recoveries` now read-modify-write
  `source_spans.metadata.formula_recovery` inside a single transaction and
  defer per-unit support/formula-status updates (each helper opens its own
  connection) until after that transaction closes — removing the nested-
  connection deadlock risk under SQLite WAL. `_clear_claim_supports` gained
  `preserve_formula=True` so a re-validation cycle keeps `formula` evidence
  rows; the ambiguous-textual-support branch now keeps
  `formula_status='preserved_in_text'` when the formula is structurally present
  instead of clobbering it to `not_applicable`. Covered by
  `test_revalidation_preserves_formula_support_rows` and
  `test_ambiguous_text_with_verified_formula_preserves_formula_status`.

- **Fix 3 — APPLIED (real bug, spec-aligned).** `recover_formula` re-validated
  only the single span under recovery, so a multi-span/multi-formula claim
  whose other formulas were recovered on *different* cited spans would fail
  re-validation purely because that evidence was dropped — contradicting
  §26.2's "re-run claim support against hydrated full raw-span text for **every
  cited span plus additive recovered evidence**." The re-validation now
  re-hydrates every `reviewed` recovery across all cited spans. Regression:
  `test_multi_span_recovery_rehydrates_prior_reviewed_evidence` (red before the
  fix — second recovery returned `uncertain`; green after — `verified` →
  `linked_evidence`).

- **Fix 4 — REJECTED (would violate the spec).** The proposed swap made
  `has_formula and not formula_ok` (→ `uncertain`/P5) precede the F6 text-fail
  gate. That changes exactly one case — *formula absent AND prose overlap fails
  (F6)* — which §26.1 mandates be `failed`: "zero/low entity intersection (the
  F6 wrong-real-span case)" is `failed` (lines 1527-1529), an F6 textual
  failure "**must not be ... routed to P5 recovery**", and "Wrong-real-span
  citations are a **release-blocking gate**" (lines 1559-1566). The legitimate
  P5-routing case (right topic, good prose, bad formula → `uncertain`) already
  works through the existing branch order because `max_cov` is high there, so
  the F6 condition is false — confirmed by
  `test_altered_formula_on_right_topic_is_uncertain`. Applying Fix 4 would have
  funnelled wrong-real-span citations — the exact defect Plan B exists to
  catch — into recovery. Spec-correct behavior is now pinned by
  `test_f6_with_absent_formula_fails_and_is_not_routed_to_recovery` (F6 +
  absent formula → `failed`, `formula_status='missing'`).

- **Fixes 1 & 2 — NOT applied (current code fails safe).** Fix 1 (reorder
  `classify_formula_loss`) is behavior-neutral: all three loss verdicts
  (`fragmented | image_only | parser_omitted`) route to recovery identically
  and the verdict is metadata-only; no oracle pins the ordering, and the
  current `fragmented`-first label is defensible when the parser cleanly
  retained the formula. Fix 2 (bidirectional sub-formula acceptance) loosens
  the §26.2 "**exactly match** an owning-claim formula" gate beyond the spec;
  the current exact-token equality is conservative (it keeps unmatched
  recoveries `uncertain` — the safe direction), and the re-validation step
  backstops acceptance regardless.

PM-review verification:

- `uv run --directory backend pytest -q` → 794 passed, 14 xfailed (the four
  Plan-B P6 oracles + ten Program 1 strict-xfail oracles remain xfail).
- `uv run --directory backend ruff check src/` → clean.
- `uv run --directory backend mypy src/` → 72 pre-existing errors, 0 in
  `claim_support.py` / `formula_recovery.py` (0 introduced).

## P6 — Staged Atomic Publish, Full-Span Hydration, And Compiler Audit (Completed)

P6 turns the four remaining Plan B strict-xfail oracles green plus two
Program-1 atlas oracles (F10, F7) it owns. Committed across four phases on
`feature/plan-b-math-distillation`:

- **P6a — F10 full-span hydration** (`feat(pipeline): F10 full-span evidence
  hydration`). `pipeline/compile.py` adds `hydrate_span_text` / `hydrate_spans`
  (+`SpanTextUnavailable`): they re-parse the registered source with the same
  deterministic parser + `spans_from_sections` that produced the stored spans
  and select the span whose `content_hash` matches — `content_hash` (SHA-256 of
  the exact span text) IS the verification key, robust to parser normalization
  and PDF text extraction. `retrieval/evidence.py` source-section and
  entity-derived items hydrate full text; an unavailable span is flagged
  `evidence_status='stale'` (new `EvidenceItem` field) and never has its preview
  silently substituted. Un-xfailed the Plan B FRM08 oracle and the Program-1
  F10 oracle (both now materialize the source file, the production
  precondition); added a drift/unreadable regression. Reconciled
  `SEARCH_ENGINE_SCHEMA §10.2` to the re-parse + content-hash mechanism. The P1
  guides already described hash-verified full-span hydration accurately
  (no guide change).

- **P6b — Compiler audit §20.5 + F7 stale-span reconciliation**
  (`feat(pipeline): compiler audit §20.5 assertions + F7 stale-span
  reconciliation`). `AuditReport` gains `dangling_supports` (#3),
  `formula_inconsistencies` (#5), `staged_leftovers`/multiple-authoritative
  (#4), `duplicate_candidates` (§20.1 hint), and `broad_fallback_plan_c` (#2,
  recorded + assigned to Plan C). `release_blocking` (failed/stale/dangling/
  formula/staged) gates lint/release; `.ok` stays the strict "all verified"
  check. **User direction (ownership split):** the only broad fallbacks in the
  codebase — `synthesis.py:110` and `community_reports.py:211` — are
  community-report/graph-derived, so per §20.5 #2 the audit RECORDS them and
  assigns them to Plan C; Plan B does NOT modify those modules. The L2/
  source-pair claim path has no broad fallback, so Plan B's removal scope is
  vacuously satisfied. `reconcile_source` now removes the edited source's stale
  spans (§26.4) via new `db.delete_source_spans` (cascades claim_supports +
  artifact_dependencies); `retire_knowledge_unit` drops its claim_supports
  (#3). Un-xfailed the Program-1 F7 oracle; reassigned the Program-1 F6
  oracle's xfail to Plan C (it stays xfail — Plan C removes the synthesis
  fallback).

- **P6c — Staged compiler generations + atomic publish**
  (`feat(pipeline): staged compiler generations with atomic publish`).
  `recompile_source` stages a source's active units in a `GEN-` generation,
  re-validates them, runs the publish-gate audit, and publishes — or, on any
  failure (the `_inject_failure` test seam, an audit violation, or a raised
  error), discards the staged generation and re-raises, leaving the prior
  authoritative generation untouched (no partial authoritative publish).
  Unchanged source + same prompt-contract version reuses the authoritative
  generation (idempotent, no count amplification). `compile_source_l2` publishes
  via this path on success and discards on a publish-gate failure.
  `AuditReport.publish_blocking` is the narrower generation gate (dangling /
  formula-inconsistency / multiple-authoritative): failed/stale claims are
  excluded from serving and surfaced by lint, so they do not block publishing
  the sound verified set. Un-xfailed the idempotent-rebuild and
  failed-compile-no-partial-publish oracles; added a production compile
  generation/idempotency regression. **D2 holdout re-arm (governance, same
  basis as the v8 schema re-arm):** P6b's `delete_source_spans` + retire cleanup
  changed `db.py`'s SHA-256; both are source-pair compiler-lifecycle helpers
  touching no retrieval/ranking/projection/`materialize_chunks` path, so the
  lexical FTS5/BM25 Q06 holdout metric is provably unaffected — re-armed the
  drift tripwire (`plan_b_p6_rearm` provenance recorded in
  `D2_HOLDOUT_RESULT.yml`).

- **P6d — `wiki lint` Compiler Integrity surface**
  (`feat(lint): wiki lint Compiler Integrity surface`). `lint.compiler_integrity`
  runs the read-only audit (§20.5) and maps findings to LintIssues:
  release-blocking violations are ERRORs (driving the existing non-zero lint
  exit for CI/testbed gating); not-yet-verified claims + duplicate candidates
  are INFO; broad-fallback findings are WARNINGs flagged Plan-C-assigned. Wired
  into `run_lint`'s fast checks (existing checks unchanged); the `wiki lint`
  summary panel gains a Compiler Integrity line. Un-xfailed the lint-surface
  oracle. The P1 USER_GUIDE/WORKFLOW_GUIDE already described the section + the
  non-zero exit accurately (no guide change).

### P6 Verification

```
uv run --directory backend pytest -q
  → 808 passed, 8 xfailed (was 794/14; +6 un-xfailed oracles now green +
    8 new regression tests; the 8 remaining xfails are Program-1 F6/F8/F9 →
    Plan C and F3/F4/F5/F11/F12 → Program 3. Zero Plan B xfails remain.)
uv run --directory backend ruff check src/  → All checks passed!
uv run --directory backend mypy src/  → 72 errors (pre-existing baseline; 0
  introduced — lint.py/compile.py/claim_support.py clean; the cli.py errors
  predate Plan B).
```

Next phase: P7 — current testbed (`gaussian_splatting`) + end-to-end compiler
audit (`VAULT_ROOT=testbed wiki status|add|update|lint`), Markdown/local-PDF/
Reference-Mode validation, with the provider-backed extraction/recovery
blocker documented if the provider is unavailable.

### P6 Review — Findings Triage (2026-06-13)

A post-P6 review raised four flaws. Verified each against the committed code +
spec before acting (per the Review Feedback Loop rule; precedent: the P5 PM
review's Fix 4 was a spec violation, so findings are not accepted blindly):

- **Flaw 1 (validate-before-reconcile) — REJECTED, false positive.**
  `compile_source_l2` already calls `validate_claim_support` for every unit
  (computing `semantic_hash` + `support_status`) BEFORE `reconcile_source`
  (compile.py lines 237-240). The reviewer's reconcile-before-validate pseudocode
  does not match the code; no change.
- **Flaw 2 (TOCTOU publish gate) — FIXED (commit `56c76aa`).** `recompile_source`
  set `generation_id` on the units before the publish-gate audit, so a failed
  audit discarded the generation after overwriting the prior authoritative
  generation's attribution (§26.3 violation). The `generation_id` UPDATE is now
  deferred until after the gate clears. Regression:
  `test_failed_publish_gate_preserves_prior_generation_attribution`.
- **Flaw 4 (unbounded SQL IN) — FIXED (commit `56c76aa`).** `delete_source_spans`
  and `hydrate_spans` now chunk their `IN (?, …)` parameter lists under
  `_SQL_VAR_CHUNK = 900` (SQLITE_MAX_VARIABLE_NUMBER). Regression:
  `test_delete_source_spans_handles_more_than_sqlite_var_limit` (1500 ids).
- **Flaw 3 (generation-scoped read visibility) — REAL §26.3 GAP, ROUTED TO
  PLAN-FIRST (NOT hot-patched).** `list_eligible_knowledge_units` does not filter
  by `compiler_generations.status`, so §26.3 ("query/evidence/search read only
  authoritative-generation rows; staged rows invisible outside the compiler")
  is not enforced. The reviewer's one-line `(authoritative OR generation_id IS
  NULL)` join is incomplete: it conflicts with the Flaw 2 fix (which keeps units
  at `generation_id IS NULL` until after the gate, so the NULL escape hatch
  still serves mid-compile/failed-audit units) and cannot satisfy both the
  compiler-internal callers (must see units under compile) and the serving
  callers (authoritative only) with one filter. Root cause: the compiler mutates
  one row set in place rather than keeping a separate staged row version. Proper
  fix is architectural (dual-context eligibility, or staged/authoritative row
  separation) — captured in `.agents/USER_REPORT.md` for a plan + approval.
  **Known P6 limitation:** §26.3 read-filtering is specified but not yet enforced;
  practical exposure is low in the current single-process compiler (the staged
  window is within one function call, not observable by concurrent queries).

## Plan B2 — Compiler Staging/Authoritative Row Separation (Completed; §26.3 enforcement)

Follow-up to P6 review Flaw 3 (§26.3 read-visibility gap). User chose
staged-row separation; a 2nd review round corrected three fatal flaws (PK
paradox → publish-time reconcile; graph leakage → graph upsert after the gate;
zero-unit guard removed). Implemented Plan-B-bounded (graph generation-scoping
stays Plan C, per user direction). Commits on `feature/plan-b-math-distillation`:

- **B2-P1 — docs-first**: SYSTEM_BEHAVIOR §26.3 (visibility gated at
  write/materialization time; copy-on-stage; publish-time reconcile; graph
  upsert after the gate; no zero-unit guard), SCHEMA §20.3/§20.5 #4 (staged
  units carry temp ids + are never materialized; discard leaves no orphan
  downstream artifact; served = authoritative ∧ verified ∧ not-retired),
  SEARCH_ENGINE §10.1 (materialize authoritative-only → retrieval/query read
  path unchanged). Guides already accurate.
- **B2-P2 — 6 failing oracles** (`test_plan_b2_staging.py`): staged units not
  served but compiler-visible; authoritative-gen-with-unchecked stored-not-served;
  successful compile persists graph + serves units; failed staged compile leaks
  no graph; zero-unit recompile publishes + retires prior; edit recompile leaves
  no dangling graph ref.
- **B2-P3 — eligibility split + backfill** (`b7942ab`): `list_serving_units`
  (authoritative ∧ verified ∧ not-retired) + `list_generation_units` (one gen);
  one-time deterministic `GEN-mig-<source_id>` backfill of legacy verified
  NULL-generation units, run from `init_db` (not every connect). No
  SCHEMA_VERSION bump (data-only; reaches existing DBs via init_db). D2 db.py
  fingerprint re-armed (`plan_b2_rearm`; eligibility/migration helpers, no
  ranking path).
- **B2-P4 — copy-on-stage compile** (`890468c`): `compile_source_l2` stages its
  extracted units in a fresh generation, validates + gates BEFORE any served
  write, and on a passing gate reconciles (stable ids carried forward), publishes
  atomically (retire prior-gen units, flip authoritative), then emits ATM + graph
  + search ONLY from the authoritative served set; a blocked gate / error discards
  the staged units + claim supports with the prior generation untouched (no orphan
  graph — graph upsert moved past the gate). `recompile_source` refactored onto
  shared publish helpers (Flaw-2-safe: attribution after the gate). Graph entities
  cite stable L1 spans, so no temp→stable graph rewrite is needed; graph
  generation-scoping remains Plan C. `materializer` + `reemit_projections` read
  `list_serving_units` (authoritative-only). Updated 3 search/projection test
  seeders to attribute their seeded units to an authoritative generation.

### B2 Verification (full CI)

```
uv run --directory backend pytest -q  -> 817 passed, 8 xfailed
uv run --directory backend ruff check src/  -> All checks passed!
uv run --directory backend mypy src/  -> 72 pre-existing errors, 0 introduced
VAULT_ROOT=$REPO/testbed wiki status  -> healthy (L1 done, L2-L4 pending)
VAULT_ROOT=$REPO/testbed wiki lint    -> Compiler Integrity clean, exit 0
npx vitest run (plugin)               -> 44 files, 361 tests passed
```

The 8 remaining xfails are Program-1 F6/F8/F9 (Plan C) and F3/F4/F5/F11/F12
(Program 3). Next: Plan B P7 — testbed end-to-end compiler audit + provider-backed
extraction/recovery (or documented blocker), then P8-P10 (role reviews, full CI,
v0.8.0 release covering B + B2).

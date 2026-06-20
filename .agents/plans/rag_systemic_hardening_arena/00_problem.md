# Briefing (00_problem): RAG Systemic Hardening

Date: 2026-06-20 | Source drafts: `.agents/drafts/batch_1_to_3_audit/` (findings 01, 02, 03, 06)

## Context: why this scope and not the others

The `batch_1_to_3_audit` drafts raised 10 findings. A grounding pass against the
**current** tree (branch `feature/rag-hardening`) proved the audit was written
against a pre-stabilization code state: six of the ten are already shipped and
pinned by regression tests, so they are **out of scope** here:

| Finding | Status in current tree | Regression test |
|---|---|---|
| 04 locator false-truth | FIXED — `_item_payload` emits `orphaned_support` (`context_service.py:428`) | `test_context_service_marks_orphaned_support_without_false_truth_state` |
| 05 budget thrashing | FIXED — `expansion_refused`/`budget_exhausted` + retry hint (`context_service.py:789`) | `test_context_expand_reports_budget_refusals_without_requeueing_same_handles` |
| 07 trace mutation | INTENTIONAL & tested — top-level arrays clear on synth-fail, but `selected_items` retains evidence and a `synthesis_status:"failed"` action is recorded (`orchestrator.py:223,246`) | `test_failed_answer_validation_clears_answer_provenance` |
| 08 CJK token overflow | FIXED — `_estimate_tokens` = `max(char, utf8_bytes//3)` (`context_service.py:198`) | `test_context_service_cjk_budget_estimator_is_conservative` |
| 09 rank destruction | FIXED — `_selected_refs_from_payloads` preserves order (`context_service.py:271`) | `test_context_service_selected_refs_preserve_pack_order` |
| 10 expansion state leak | FIXED — `context_expand` mutates `updated_omitted`/`updated_selected` (`context_service.py:811`) | `test_context_expand_consumes_successful_handles_once` |

This milestone therefore covers only the **genuinely unimplemented systemic
work**: 06, then 02, 03, 01.

## The four problems to solve

### P-06 — Explore route bypasses ContextService (concrete, smallest)
`QueryOrchestrator.run` branches at `route != "explore"` (`orchestrator.py:119`)
and for `explore` calls the legacy `evidence_mod.build_evidence` directly,
manually minting a `QTR-*` id and a parallel `retrieval_trace`. `_ADMITTED_ROUTES`
(`context_service.py:29`) deliberately excludes `explore` and §31.8 documents the
deferral. Consequence: explore generates no `PACK-*`/`SNAP-*`/`CTXA-*`, enforces
no `limit_tokens` via `_apply_budget`, and forks the trace schema — blocking
cross-client parity and Plan F P8 completion.
**Goal:** explore obtains its grounding evidence through `ContextService.context_fetch`
(same snapshot/budget/trace contract); the explore-specific behavior (follow-up
questions + insight candidates) becomes a *synthesis-phase consumer* of the
normalized pack, not a divergent retrieval path.

### P-02 — Graph fragmentation vs. giant components
Auto-merge of entities is banned (homonym safety). Result: "LLM" / "Large
Language Model" / "LLMs" spawn disconnected subgraphs → graph-guided expansion
halts early → recall loss. The opposite failure (over-loose edges → a giant
component that drains the token budget on noise) is equally fatal. Foundations
already exist: `graph_entities(canonical_name, entity_type)` unique index,
`graph_relations.quarantine_reason` + `lifecycle_status` (`db.py:339,358`).
**Goal:** a **soft-link / candidate-alias** edge type that is NOT traversed in
factual routing but MAY be traversed under explore with a budget penalty, plus a
**giant-component quarantine** that excludes hub nodes above a density threshold
from automated traversal. No autonomous entity merging.

### P-03 — Strict pipeline fragility (domino + snapshot paralysis)
A single dropped `span_id` in the parser orphans a reference that the strict
`ContextService` locator validation then discards/errors. Separately,
`expected_snapshot_id` validation (`context_service.py:537,743`) hard-rejects any
expansion once a background ingest changes the epoch, even when the agent's pack
cites only untouched notes. Foundations exist: `_source_epoch`/`_snapshot`/
`_conflict_response`, and the on-demand `compiler_integrity` lint (§26.5).
**Goal:** (a) **soft-snapshot auto-rebase** — downgrade `snapshot_conflict` to an
allowed rebase when the changed epoch does not intersect the pack's cited nodes;
(b) **pipeline healing** — an async integrity pass that detects/repairs/flags
orphaned `source_span_ids` and broken locators before they reach the synchronous
path. Reuse the existing `compiler_integrity` checks, do not duplicate them.

### P-01 — Oracle overfitting (methodology)
The Failure Atlas (F01–F13, `qrels.yml`, `support_labels.yml`, D2 holdout) is a
frozen synthetic baseline. Risk: the system optimizes to pass clean fixtures
while degrading on real, noisy notes. The P7 `context_feedback`/`FBK-*` loop
exists but failing real queries never become new fixtures.
**Goal:** (a) **real-world sampling** — promote captured failing queries
(`irrelevant`/`incorrect`/`insufficient` FBK events) into candidate adversarial
fixtures; (b) **noise-injection** evaluation — mandate degraded-input cases
(missing headers, broken tables, OCR errors) so the baseline measures resilience.

## Hard constraints (locked, non-negotiable)
- **No autonomous entity merging** (System Invariant + homonym safety). Soft-links
  are proposals, never silent identity merges.
- **DB = single source of truth**; `.curator/Collections` markdown is derived.
- **No new external search-binary dependencies.**
- **Spec-first**: every contract change lands in `docs/specs/{system_behavior,
  curator_schema}` (and `_KR` guides) before code.
- **Schema migrations** are forward-only with `PRAGMA integrity_check` gates and an
  idempotent unchanged-rebuild (precedent: §26.5, migration v9).
- **Do not regress** the six already-fixed findings or their tests.

## Definition of done
Each sub-feature ships behind its own phase with `pytest` + `ruff` + `mypy`
green, docs/specs synchronized EN→KR, and a testbed smoke pass. Explore produces
a `PACK-*`/`SNAP-*` trace identical in shape to local/global. Factual routing
never traverses soft-links. A non-intersecting epoch change no longer blocks
expansion. At least one real captured failure can be promoted to a fixture, and
the eval suite includes noise-injected cases.

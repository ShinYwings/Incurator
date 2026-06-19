# Failure Atlas — Diagnostic Contract (Program 1, D2 observatory)

Current version: v0.7.0 (D2 observatory release)
Plan of record: `.agents/plans/D_current_system_failure_atlas.md` (Git history
after release); umbrella program:
`.agents/plans/03_rag_knowledge_quality_stabilization.md`.

This spec defines the **Failure Atlas**: the versioned, machine-readable record
of every suspected end-to-end quality failure in the Incurator RAG/DAG system
(F1–F13 from the stabilization umbrella plan), the status lifecycle each record
must follow, the evidence-bundle identities every diagnostic result must
declare, and the contract tests that enforce all of it.

The atlas is the **truth contract** that Program 2 (Evidence Compiler
Integrity) and Program 3 (Agentic Query Serving & Sensemaking) consume. Those
programs cite atlas case ids and oracle versions; they may not silently
redefine an oracle. Plan D2 (final specification + minimum Quality Observatory)
resumes from this baseline after Plan E (external research) merges.

## 1. Authoritative Locations

| Artifact | Location |
|---|---|
| This contract spec | `docs/specs/failure_atlas/FAILURE_ATLAS.md` |
| Case records (machine-readable, authoritative) | `docs/specs/failure_atlas/cases/F01.yml` … `F13.yml` |
| Evaluation baseline & release gates | `docs/specs/failure_atlas/EVALUATION_BASELINE.md` |
| D2 one-shot holdout result | `docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml` |
| Final Program 2/3 handoffs | `docs/specs/failure_atlas/PROGRAM_HANDOFFS.md` |
| Frozen fixture corpus + qrels | `docs/specs/failure_atlas/fixture_corpus.yml`, `docs/specs/failure_atlas/qrels.yml` |
| Query-level minimal support labels | `docs/specs/failure_atlas/support_labels.yml` |
| Contract tests (schema/lifecycle enforcement) | `backend/tests/test_failure_atlas_contract.py` |
| Deterministic reproductions (baseline + oracle) | `backend/tests/test_failure_atlas_repro.py` |
| Mutation/degradation/parity experiments | `backend/tests/test_failure_atlas_experiments.py` |
| Evaluation baseline runner | `backend/tests/test_failure_atlas_eval.py` |

The YAML case records are the single machine truth for case status. This
markdown describes the schema and lifecycle; if the two diverge, both are wrong
and must be reconciled in the same change (repo Architecture Source Of Truth
rule).

## 2. Case Record Schema

Each `cases/F*.yml` file holds exactly one record with these fields:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | `F1`…`F13` | yes | Stable case id from the umbrella plan §4. Never renumbered. |
| `title` | string | yes | One-line failure statement. |
| `query_family` | enum | yes | Primary family in which the failure manifests: `direct-factual`, `associative`, `global`, `source-scoped`, `cross-route`, `compiler`, `client-parity`, `evaluation-infra`. Per-family reporting is mandatory; aggregate-only claims are prohibited. |
| `execution_mode` | enum | yes | `deterministic` (provider-free), `provider` (configured LLM/embedder required), `degraded` (missing-provider behavior), `human-review` (semantic judgment). Modes are never mixed in one result. |
| `status` | enum | yes | Current classification: `suspected`, `reproduced`, `disproven`, `accepted`, `assigned`, `retired`. |
| `status_history` | list | yes | Ordered `{date, status, evidence}` entries. First entry must be `suspected`. Transitions must follow §3. The last entry's status must equal `status`. |
| `owner` | enum | yes | Who owns the next action: `plan-d2`, `program-2`, `program-3`, `plan-e`, `unassigned`. |
| `impact` | string | yes | What truth/quality property is lost while unfixed. |
| `boundary` | object | yes | Exact loss/corruption boundary: `module` (repo-relative path), `symbol` (function/class), optional `detail`. |
| `fixture` | string | reproduced/assigned | Pytest node id (`backend/tests/<file>.py::<test>`) of the minimal deterministic reproduction. |
| `commands` | list of strings | reproduced/assigned | Exact commands that reproduce the result. |
| `oracles` | object | yes | `deterministic` and/or `semantic` oracle statements; at least one non-null. `execution_mode: deterministic` requires a deterministic oracle. The oracle defines what *correct* behavior will look like — Programs 2/3 must satisfy it verbatim or renegotiate via a new atlas version. |
| `before_state_evidence` | string | reproduced/assigned | Captured current-behavior evidence (code boundary + observed result) recorded BEFORE any repair. |
| `observed_result` | string | yes | What the reproduction actually showed at the baseline snapshot. |
| `snapshot` | object | yes | Identity of the measurement: `git_sha` (40-hex), `version` (semver), `schema_version` (int), `scenario` (active testbed scenario name). |
| `assignment` | object | status=assigned | `{program, gate}` — downstream program and the release gate that will retire this case. |
| `resolution` | object | status=retired | `{version, evidence, after_state}` — release and exact passing contract that retired the case. |
| `notes` | string | no | Anything that doesn't fit above (secondary families, partial passes). |

A valid `source_span_id` is never treated as proof of claim support: oracles
must distinguish id validity, support correctness, support completeness,
locator resolution, and freshness where applicable.

## 3. Status Lifecycle

```text
suspected ──> reproduced ──> assigned   (routed to plan-d2 / program-2 / program-3)
    │              └───────> accepted   (explicit limitation w/ user-visible contract)
    └───────> disproven                 (concern measured and rejected)
                              assigned ──> retired (assigned gate satisfied)
```

Allowed transitions: `suspected→reproduced`, `suspected→disproven`,
`reproduced→assigned`, `reproduced→accepted`. Everything else (including
skipping `reproduced` on the way to `assigned`) is rejected by the contract
tests. D2 adds `assigned→retired` when the assigned release gate is satisfied
with explicit after-state evidence.

Rules:

- No transition to `reproduced` without a minimal fixture, commands, and
  before-state evidence.
- No transition to `accepted`/`assigned` without an owner, impact, and (for
  `assigned`) the downstream gate.
- No production behavior may be repaired before its case carries before-state
  evidence (capture-before-repair).

## 4. Evidence-Bundle Contract (deliverable D3)

Every diagnostic result — pytest reproduction, mutation experiment, or
evaluation run — must declare:

- **Run identity**: the pytest node id (or experiment name) plus the atlas case
  id(s) it serves.
- **Corpus/config/model identity**: the snapshot block (git SHA, package
  version, DB schema version, active scenario) plus, for provider runs, the
  provider/model fingerprints (`embedder.fingerprint`, `reranker.fingerprint`,
  LLM identity from `llm_identity`).
- **Normalized request and selected evidence**: the query/request issued and
  the record/span ids selected.
- **Exact support/locator references**: which `source_span_ids`/record ids back
  each claim made by the diagnostic.
- **Warnings and degradation**: every fallback mode and warning surfaced.
- **Retention/privacy**: diagnostic evidence defaults to synthetic/testbed
  sources; private live-vault excerpts are never persisted in the repository
  without explicit user approval.

In D1 the evidence bundles were encoded as deterministic pytest modules plus
the case records. D2 adds a provider-free fine-grained evaluation result
contract. Every result reports per query family, preserves ranked record and
span identities, records indexed-character cost and latency, and keeps
aggregate-only metrics out of release gates.

## 5. Execution-Mode Separation

Deterministic provider-free gates, configured-provider benchmarks, degraded
modes, and human semantic review are reported separately and never combined
into a single pass/fail. D1 ships only `deterministic` and `degraded`
reproductions; `provider` and `human-review` cases are recorded as such in
`notes` and scheduled for D2/E where needed.

## 6. Reproduction Test Conventions

Two test kinds, both in `backend/tests/test_failure_atlas_repro.py`:

1. **Baseline tests** (`test_f<N>_baseline_*`) assert the **current defective
   behavior**. They PASS today by construction; they are the captured
   before-state evidence. If a baseline test starts failing, the system's
   behavior changed without the atlas being updated — that is a contract
   violation, not a fix.
2. **Oracle tests** (`test_f<N>_oracle_*`) assert the **desired contract** and
   are marked `@pytest.mark.xfail(strict=True)`. They XFAIL today (the failure
   is reproduced). When a downstream program fixes the behavior, the test
   XPASSes and pytest fails the suite — forcing the fixer to deliberately
   remove the marker, flip the atlas record out of `assigned`, and update the
   baseline test in the same change. This is the mechanical handoff that
   prevents silent oracle redefinition.

The D1 release gate "all known failures reproducibly classified" means: every
case record validates against §2/§3, every `reproduced`/`assigned` case has a
green baseline test and an XFAILing oracle test, and the full suite passes.

## 7. Case Index (status at v0.6.0 baseline)

| Id | Title | Family | Status | Owner |
|---|---|---|---|---|
| F1 | Search-hit provenance dropped at `EngineHit→SearchHit` conversion and evidence assembly | direct-factual | retired | unassigned |
| F2 | One logical query persists ≥2 disconnected `QTR-` traces | cross-route | retired | unassigned |
| F3 | `CurationPolicy` (KRS) not enforced through evidence assembly | cross-route | assigned | program-3 |
| F4 | Global evidence is query-independent; source-scoped evidence unbounded | global | assigned | program-3 |
| F5 | Context packing is a fixed 16,000-char cutoff with silent omission | cross-route | assigned | program-3 |
| F6 | Synthesis items without declared spans grounded to ALL upstream spans | compiler | assigned | program-2 |
| F7 | Rebuild idempotency/atomicity/dependency-closure invalidation unproven; stale L1 rows linger after edits | compiler | assigned | program-2 |
| F8 | Exact-name entity merging (homonym false-merge) and connected-component giant communities | compiler | assigned | program-2 |
| F9 | Authored note topology (wikilinks/embeds/tags) never compiled into the graph | compiler | assigned | program-2 |
| F10 | Searchable span evidence capped at a 200-char preview | source-scoped | assigned | program-2 |
| F11 | Explore is a single prompt pass — follow-ups are rendered, never executed | associative | assigned | program-3 |
| F12 | External MCP and Obsidian plugin do not share one normalized context contract | client-parity | assigned | program-3 |
| F13 | Active testbed scenario validates retired EXH/search-era architecture | evaluation-infra | retired | unassigned |

All thirteen cases were reproduced deterministically at the v0.6.0 baseline.
D2 retires F1, F2, and F13 by satisfying their frozen oracles; F3-F12 remain
assigned to Program 2 or Program 3.

## 8. Downstream Handoff (deliverable D5, D1 portion)

- **Plan D2 (Quality Observatory)** owns: F1 (critical provenance adapter — the
  only repair P5 may make, because unresolved hit-provenance invalidates every
  retrieval measurement), F2 (authoritative query-transaction identity /
  parent-child trace model), F13 (current-architecture scenarios).
- **Program 2 (Evidence Compiler Integrity)** owns: F6, F7, F8, F9, F10 — gates
  are written into each case's `assignment.gate` and mirror umbrella §9.
- **Program 3 (Agentic Query Serving)** owns: F3, F4, F5, F11, F12 — gates
  mirror umbrella §10.
- **Plan E (External Research Design Matrix)** must benchmark candidate
  techniques against the reproduced failures by atlas id (no technique adoption
  without a reproduced target failure).

## 10. D2 Fine-Grained Evaluation And Holdout Contract

Every retrieval release gate reports separately for each query family:

- Recall@1/3/5 and MRR;
- top-1 citation correctness and citation completeness against expected spans;
- provenance resolution rate;
- hard-negative outrank count;
- indexed-character cost and latency.

Aggregate-only quality claims and model-judge-only gates are prohibited. The
Failure Atlas `Q06` has one valid D2 measurement under the frozen D1 corpus,
qrels, lexical engine configuration, and no-tuning procedure. Two earlier runs
were audit-invalidated while provenance resolution, citation pairing,
preflight gates, and execution identity were hardened. All three runs used the
identical ranking configuration and are recorded transparently. The committed
`D2_HOLDOUT_RESULT.yml` is authoritative; CI validates it but does not rerun
the holdout.

The frozen D1 holdout contains only direct-factual Q06. Associative,
source-scoped, and global families are still reported separately on their
available deterministic or structural oracles, but realistic holdout coverage
for those families is an explicit downstream evaluation requirement, not a
claim made by D2.

## 9. Privacy And Retention

All fixtures and corpora under this contract are synthetic. The frozen fixture
corpus (`fixture_corpus.yml`) contains invented technical prose written for
this repository. No live-vault content, file names, or excerpts may be added to
atlas artifacts without explicit user approval recorded in the case `notes`.

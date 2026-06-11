# Program 1E External Research Design Matrix Master Plan

Date: 2026-06-11
Status: DRAFT — Arena debate concluded; planning/research approval required; no production implementation authorized

Arena:
`.agents/plans/external_research_design_matrix_arena/`

Umbrella dependency:
`.agents/plans/03_rag_knowledge_quality_stabilization.md`

## 0. Purpose And Terminal Condition

This is the Program-1 deep external primary-source research and comparative-spike
plan. It answers which external techniques should shape later Incurator
specifications. It does not implement those techniques.

The terminal output is an approved, evidence-backed decision package:

1. primary-source candidate dossiers;
2. frozen comparative evaluation protocol;
3. reproducible disposable spike reports;
4. narrowly scoped `adopt-contract`, `benchmark-later`, or `reject-default`
   decision records;
5. downstream specification requirements for Programs 1, 2, and 3;
6. rejected-technique register with revisit triggers.

No production code, production schema, static spec, guide, version, changelog,
runtime dependency, or plugin behavior changes are in scope for this plan.

## Strict Quality Condition

- No candidate is approved without a reproduced Incurator failure or a clearly
  documented architecture-neutral control question.
- No claimed mechanism is accepted without checking its primary paper and
  official implementation/documentation where available.
- No comparative result is accepted without an unchanged baseline, simplest
  plausible control, frozen validation set, untouched holdout, raw per-case
  results, and reproducible environment manifest.
- Decisions are scoped by failure, query/task family, source type, and tested
  scale. Aggregate-only decisions are prohibited.
- Direct factual quality, exact provenance, deterministic reproducibility,
  bounded cost, and update/delete behavior are hard constraints.
- Model judges are supplementary only and must be calibrated against
  human/deterministic labels.
- All spikes operate on immutable exports or copied disposable databases and
  cannot mutate the production vault, production `state.sqlite`, `03_Notes/`,
  `04_Resources/`, or `06_Archives/`.
- This plan ends before production implementation.

## Locked Design Decisions (Arena Consensus)

1. **Failure-first, mechanism-level research.** Start from reproduced failures
   and isolate candidate mechanisms. Framework names are not architecture
   authority.
2. **Primary-source claims, local proof.** Papers and official docs define the
   candidate claim; only local comparative evidence establishes an Incurator
   decision.
3. **Three decision classes.**
   - `adopt-contract`: accept an invariant or requirement for downstream specs;
     it does not authorize implementation.
   - `benchmark-later`: retain as a candidate gated on a trusted substrate or
     larger controlled experiment.
   - `reject-default`: prohibit as the default in the measured scope and record
     a revisit trigger.
4. **Layered evaluation.** Measure retrieval, evidence, answer/agent task, cost,
   latency, reproducibility, and update behavior separately.
5. **Per-family reporting.** Report direct factual, source-scoped, associative/
   multi-hop, broad/global, contradiction/verification, agentic, freshness, and
   cross-client families independently.
6. **Immutable spike boundary.** Research artifacts may read frozen exports and
   copied databases. They cannot enter production import paths or dependencies.
7. **Role separation.** Dossier author, spike executor, and decision reviewer
   must be distinct review roles, even if simulated sequentially by one agent.
8. **No hidden implementation approval.** Adoption of a principle cannot be
   interpreted as approval to modify production code. Later Program plans,
   specs-first work, and user approval remain mandatory.

## Scope

### Required Candidate Matrix

| Candidate family | Primary comparison | Failure/task focus | Earliest downstream owner |
|---|---|---|---|
| Context-enriched chunks | current chunks; deterministic heading-context control | long technical sections, direct/source-scoped retrieval | Program 2/3 |
| Passage/entity PPR | current memory paths; hybrid-only control | associative and multi-hop recall | Program 3 |
| Denoised hierarchy / Leiden candidate | connected components; authored-topology control | global structure, giant components, stability | Program 2 |
| Query-relevant global / DRIFT-like flow | current global/explore routes | broad questions without unbounded evidence | Program 3 |
| KG-guided expansion/organization | seed hybrid retrieval | coherent multi-hop evidence packs | Program 3 |
| Retrieval sufficiency/corrective gate | one-shot baseline | weak/insufficient initial retrieval | Program 3 |
| Complexity-aware routing | current router and fixed-route controls | route accuracy and cost | Program 3 |
| Bounded iterative retrieval | one-shot baseline | agent task completion | Program 3 |
| Progressive context disclosure | fixed 16,000-character block simulation | context precision/recall per token | Program 3 |
| Fine-grained RAG/citation diagnostics | current tests and deterministic labels | observatory/release-gate quality | Program 1 |
| Selective formula recovery | current extraction and parser-only controls | proven formula-loss fixtures | Program 2 |

### Explicit Non-Goals

- Production reranker or RRF tuning.
- Production `ContextService`, graph, compiler, or formula-recovery code.
- New production database tables or migrations.
- Framework replacement or new production dependencies.
- Public-benchmark score chasing.
- Web retrieval as a substitute for vault evidence.

## Dependencies And Entry Gates

### Hard Dependencies

- Approved and merged Plan D1 Failure Atlas records, baseline identities,
  labeling methods, and experiment/evidence-bundle contract.
- A confirmed active testbed scenario or approved creation of research-specific
  immutable fixtures.
- Exact baseline repository SHA, environment, current schema, provider/model
  versions, and copied database/export hashes.
- Initial deterministic/human labels for the query/task families being tested.

Plan E starts from `master` only after Plan D1 is merged with a valid frozen
baseline. It uses a separate Program-1 research branch and release/rollback
boundary.

### Dependency Boundaries

- Final graph/hierarchy conclusions may remain `benchmark-later` until Program 2
  supplies a trusted graph and stable knowledge IR.
- Final ContextService/agentic-serving conclusions feed
  `.agents/plans/F_agent_context_service.md` but do not authorize it.
- Research that discovers a new production defect records it for the Program-1
  Failure Atlas; it is not fixed under this plan.

## Evidence Ledger

This ledger is completed and frozen before the first spike runs.

### Current Repository And Schema Reality

- Baseline branch/SHA: record at execution start.
- Current retrieval entry points:
  `backend/src/curator/retrieval/engine.py`,
  `backend/src/curator/retrieval/evidence.py`,
  `backend/src/curator/retrieval/orchestrator.py`,
  `backend/src/curator/retrieval/models.py`.
- Current durable query storage:
  `query_traces` in `backend/src/curator/db.py`.
- Current external surface:
  `curator_query`, `curator_fetch_context`, and raw search in
  `backend/src/curator/mcp_server.py`.
- Current Obsidian context behavior:
  `plugin/src/ui/chatSidebar.ts`, `plugin/src/context/*`,
  `plugin/src/ui/incuratorQueryTrace.ts`.
- Verified starting failures are inherited from the umbrella Failure Atlas and
  must be independently reproduced before candidate comparison.

### Current Dirty Worktree

- The workspace contains changes from other agents/users.
- Execution must record `git status --short --branch` and must not modify,
  revert, stage, or include unrelated files.
- This plan owns research artifacts only when execution is approved; it does not
  authorize edits now.

### Primary-Source Evidence

The seed matrix includes GraphRAG, LazyGraphRAG, HippoRAG/HippoRAG 2, RAPTOR,
LightRAG, KG2RAG, Contextual Retrieval, CRAG, Adaptive-RAG, Self-RAG, RepoCoder,
CodeRAG-Bench, MemGPT, RAGChecker, RAGAS, GraphRAG-Bench, KILT, ALCE, Leiden,
and Nougat. Each source must be rechecked at execution time and its precise
mechanism/claim boundary recorded.

### Rollback Requirements

- Research runs use immutable exports or copied disposable DBs.
- Record hashes of fixture exports and copied DBs before each spike wave.
- Spike scripts/configs must be isolated from production imports and removable
  without affecting the application.
- If any spike touches production/testbed state unexpectedly, stop, preserve
  evidence, restore only the copied research state, and return to planning. Do
  not revert other agents' workspace changes.
- After three repeated invalid or non-reproducible runs, activate
  `rollback_strategist`: discard that spike's conclusions and return to the
  hypothesis/protocol phase.

## Research Artifact Contracts

### Candidate Dossier

Every dossier contains:

- candidate id/name/version;
- exact primary sources and official implementation;
- mechanism and required assumptions;
- claimed benefit and reported benchmark scope;
- target Incurator failure/question;
- falsifiable hypothesis;
- provenance/update/cost/dependency risks;
- simple controls and alternatives;
- proposed spike and metrics;
- evidence against adoption;
- preliminary decision and confidence.

### Spike Manifest

Every spike freezes:

- fixture ids and content hashes;
- development/validation/holdout partitions;
- baseline and control configurations;
- candidate configuration and independent variable;
- seeds, provider/model versions, prompts, tokenizers, hardware, and environment;
- commands;
- raw result output locations;
- mutation guard confirmation.

### Decision Record

Every final record contains:

- `adopt-contract`, `benchmark-later`, or `reject-default`;
- decision scope;
- evidence and counter-evidence;
- per-family results and confidence;
- provenance, update, latency, cost, and dependency implications;
- rejected alternatives;
- downstream contract/spec owner;
- revisit trigger.

## Execution Phases (Research-TDD And CI At Each Phase)

### P0 — Baseline And Research Safety Ledger

Actions:

- confirm branch/SHA and dirty-worktree boundaries;
- confirm active scenario(s) or define immutable research fixtures;
- export/copy all research inputs;
- record schema, provider/model, prompts, tokenizer, hardware, and dependency
  versions;
- add mutation guards and verify copied-state-only execution;
- reproduce the umbrella Failure Atlas items relevant to each candidate family.

Research-TDD:

- write assertions that fixture hashes remain unchanged;
- write baseline repeatability checks;
- write expected failure reproductions before candidate spikes.

Verify:

- unchanged baseline runs are deterministic within approved tolerances;
- no production/testbed authoritative state changes;
- every candidate has a reproduced target or architecture-neutral question.

Quality gate:

- stop if baseline or labels are not stable enough to compare.

### P1 — Candidate Dossiers And Claim Fact-Checking

Actions:

- deepen each primary-source dossier;
- inspect paper, official docs, reference implementation, benchmark protocol,
  licensing, and operational assumptions;
- extract only claims relevant to the target failure;
- record independent limitations/counter-evidence where available;
- define simple controls and falsifiable hypotheses.

Research-TDD:

- dossier completeness validator checks required fields and primary-source links;
- claim-to-spike mapping test rejects untestable or unscoped claims.

Verify:

- every candidate claim maps to a measurable spike;
- no framework-level adoption language remains;
- every dossier has a risk and rejection section.

Quality gate:

- reject candidates whose mechanism or claimed benefit cannot be isolated or
  meaningfully evaluated under Incurator constraints.

### P2 — Freeze Evaluation Specification

Actions:

- define development, validation, untouched holdout, and adversarial partitions;
- define deterministic labels, claim-support labels, route/task labels, and
  human-review sampling;
- freeze per-family metrics and pass/fail interpretation;
- define cost, latency, update/delete, and provenance audit protocol;
- calibrate any model judge against labeled examples.

Research-TDD:

- metric unit tests using hand-computable fixtures;
- partition leakage checks;
- label-schema validation;
- budget/cost accounting checks.

Verify:

- metrics reproduce expected hand-computed values;
- holdout remains inaccessible to tuning;
- each decision-relevant claim has a metric and oracle.

Quality gate:

- stop if a metric cannot distinguish the target failure from a plausible false
  positive.

### P3 — Wave A: Retrieval Units And Evaluation Controls

Actions:

- compare current chunks, deterministic heading-context control, and
  context-enriched chunks;
- compare current hybrid baseline with lexical-only/vector-only controls;
- evaluate fine-grained retrieval/citation diagnostics.

Verify:

- direct factual and source-scoped results reported separately;
- source text remains distinct from generated context;
- update cost and contextualization cache/invalidation assumptions recorded.

Decision gate:

- contextual chunks can be `adopt-contract` only if exact source provenance is
  preserved and direct factual quality does not regress beyond tolerance.

### P4 — Wave B: Graph, Hierarchy, And Global Mechanisms

Actions:

- compare current memory paths with passage/entity PPR;
- compare connected components with denoised/seeded hierarchy candidates;
- compare current global/explore routes with query-relevant community selection;
- compare seed retrieval with graph-guided expansion/organization.

Verify:

- associative/multi-hop and broad/global families reported separately;
- graph additions carry explainable seeds/paths and evidence;
- direct factual non-regression, giant-component ratio, seed stability,
  update/delete behavior, and expansion budget measured.

Decision gate:

- conclusions requiring a trusted Program-2 graph remain `benchmark-later`.

### P5 — Wave C: Adaptive, Corrective, Iterative, And Progressive Serving

Actions:

- simulate measured complexity routing;
- compare one-shot with sufficiency-gated corrective retrieval;
- compare one-shot with bounded iterative retrieval;
- compare fixed context block with progressive disclosure and reserved expansion.

Verify:

- stop rules, maximum iterations, and budget accounting are explicit;
- agent task success, context precision/recall per token, latency, and degradation
  are measured;
- no iteration can become unbounded or silently mix snapshots.

Decision gate:

- any accepted contract is fed to the Program-3 ContextService plan and remains
  unimplemented here.

### P6 — Wave D: Conditional Formula Recovery

Actions:

- prove the exact parser/distillation loss boundary on formula fixtures;
- compare current extraction, parser-only controls, and selective recovery;
- measure formula recall, hallucinated replacement, cost, and update behavior.

Verify:

- raw evidence is never overwritten;
- low-confidence recovered content remains explicitly uncertain;
- whole-corpus heavy recovery is separately costed.

Decision gate:

- reject default VLM processing unless selective recovery has a measured,
  provenance-safe win.

### P7 — Untouched Holdout, Red Team, And Decision Synthesis

Actions:

- run final untouched holdout once under frozen configurations;
- conduct provenance, benchmark-leakage, framework-bias, cost, and update red
  teams;
- author scoped decision records;
- map accepted contracts/candidates to Programs 1, 2, and 3 specifications;
- record rejected defaults and revisit triggers.

Verify:

- raw results support every decision;
- decision reviewer did not tune the candidate;
- no aggregate result hides a family regression;
- no decision authorizes production implementation.

Quality gate:

- any failed holdout/provenance audit downgrades `adopt-contract` to
  `benchmark-later` or `reject-default`.

### P8 — Research Validation And Handoff

Actions:

- validate artifact completeness and link integrity;
- run applicable research-artifact tests and full local CI to prove the
  planning/research work did not disturb production;
- present the decision package for approval;
- hand specification requirements to the remaining Program-1 specification
  package and later Program plans.

Local CI:

```bash
export UV_PROJECT_ENVIRONMENT="$(git rev-parse --show-toplevel)/.venv"
uv run --directory backend pytest -q
uv run --directory backend ruff check src/
uv run --directory backend mypy src/
npx vitest run -c ./plugin/vitest.config.ts
```

Testbed:

- run only against the confirmed active scenario or immutable copied research
  scenario;
- verify the production/testbed authoritative state is unchanged after research.

Terminal gate:

- stop after user approval of the research decision package;
- do not proceed into implementation under this plan.

## Candidate-Specific Decision Gates

### Context-Enriched Chunks

- Must preserve exact raw-source linkage.
- Must beat deterministic heading-context control, not only current chunks.
- Must define cache/invalidation behavior.
- Must not materially regress direct factual retrieval.

### PPR And Graph-Guided Expansion

- Must expose seeds, traversed paths/edges, and added evidence.
- Must improve associative/multi-hop tasks without hard-negative or factual
  regression beyond tolerance.
- Must remain budget bounded and robust to noisy bridge edges.

### Hierarchy And Global Retrieval

- Must be deterministic/seed-stable under the approved contract.
- Must avoid unexplained giant components.
- Must rank/select query-relevant communities rather than load all reports.
- Must define source-edit invalidation and stale-summary behavior.

### Adaptive/Corrective/Iterative Retrieval

- Must have measured route/sufficiency or stop rules.
- Must have explicit maximum iterations, latency, and token budgets.
- Must outperform a simple fixed-route/control policy on task success or
  context-efficiency.

### Progressive Disclosure

- Must report omissions and expansion handles.
- Must preserve snapshot identity across expansion.
- Must improve context precision/recall per token or agent task success.

### Selective Formula Recovery

- Must target proven extraction loss.
- Must preserve raw evidence and uncertainty.
- Must demonstrate that benefit justifies provider/dependency/cost impact.

## Required Quality Gates

- 100% dossiers have primary-source claim boundaries and risks.
- 100% spikes have immutable manifests and reproducible commands.
- 100% decisions link a target failure/question, raw results, and downstream
  specification owner.
- 0 decisions based only on aggregate score or model judge.
- 0 production-authoritative mutations.
- 0 adopted contracts that silently authorize implementation.
- All final holdout and provenance audits pass, or decisions are downgraded.

## Stop Conditions

- Stop if the active scenario or immutable research corpus cannot be confirmed.
- Stop if baseline repeatability or labels are inadequate.
- Stop if a spike needs production schema/runtime changes.
- Stop if the candidate cannot preserve source/evidence distinction.
- Stop after three invalid/non-reproducible runs and return to protocol design.
- Stop after the approved decision package; implementation belongs to later
  approved plans.

## Final Deliverables

- Complete candidate dossier set.
- Frozen evaluation and experiment specification.
- Raw and summarized comparative spike reports.
- Adopt-contract / benchmark-later / reject-default ADR set.
- Provenance, cost, latency, update, and dependency risk register.
- Rejected-default register with revisit triggers.
- Downstream Program-1/2/3 specification map.
- Evidence ledger with final baseline and holdout results.
- Explicit D2 handoff containing adopted contracts, rejected defaults, migration
  implications, and unresolved research limits for final specification synthesis.

# RAG & Knowledge Quality Stabilization — Umbrella Program Plan

Date: 2026-06-11
Status: DRAFT UMBRELLA PLAN — top-level framing and six component Arenas concluded; implementation blocked until the current PR merges and plans are approved

## 0. Purpose

Incurator must let external agents and the Obsidian agent use a notes vault the
way a coding agent uses a codebase, while respecting that notes contain human
meaning rather than executable symbols.

The system must:

1. preserve note/PDF source truth and native structure;
2. compile meaningful, reusable prior knowledge from that truth;
3. maintain a faithful RAG + DAG hybrid as the vault changes;
4. let agents discover and progressively retrieve only the context needed;
5. make every reused claim verifiable against exact source evidence;
6. preserve corrections, contradictions, insights, and promotions with lineage.

The primary product is **trusted reusable prior knowledge delivered as bounded,
source-grounded evidence packs**. Better top-k search, more graph nodes, and more
summaries are implementation means, not success criteria.

## 1. Planning Status And Mandatory Work Order

This file is the root-level synthesis that coordinates six independent component
plans. It preserves the shared product thesis, three-program ordering, global
quality contract, and cross-plan dependencies. It is not disposable, but it is
also not an implementation-ready component plan.

Each component owns a dedicated Arena folder and root-level Master Plan using
`.agents/PLAN_TEMPLATE.md`:

```text
A  rag_retrieval_provenance_arena/
   -> A_rag_retrieval_provenance.md
B  math_extraction_distillation_arena/
   -> B_math_extraction_distillation.md
C  graph_quality_arena/
   -> C_graph_quality.md
D  current_system_failure_atlas_arena/
   -> D_current_system_failure_atlas.md
E  external_research_design_matrix_arena/
   -> E_external_research_design_matrix.md
F  agent_context_service_arena/
   -> F_agent_context_service.md
```

The top-level `rag_knowledge_quality_stabilization_arena/` records only the shared
reframing debate that established the three-program sequence. The A-F plans are
not duplicate fragments of this document: each is an independently reviewable
plan with its own problem, trade-offs, release gates, and implementation phases.

### Three execution batches

1. **Batch 1 / Program 1 — establish truth before changing algorithms**
   - D1: reproduce/classify failures and freeze the baseline/oracle contract.
   - E: research and benchmark external solution candidates.
   - D2: synthesize final target specifications and implement the approved
     minimum Quality Observatory substrate.
   - Order: D1 baseline/oracles → E comparisons → D2 final specification and
     observatory release.
2. **Batch 2 / Program 2 — repair the evidence compiler**
   - B: source-pair, formula, semantic-unit, and claim-support integrity.
   - C: entity/relation resolution and hierarchical community quality.
   - Order: B establishes stable claim/support identity, then C compiles the
     graph and hierarchy from that trusted substrate.
3. **Batch 3 / Program 3 — serve trusted prior knowledge**
   - A: measured retrieval, provenance continuity, and locator resolution.
   - F: unified external/Obsidian ContextService and feedback lineage.
   - Order: A produces the transport-neutral retrieval result, then F exposes it
     consistently to agents and clients.

Plans inside one batch execute in the stated order on separate branches/releases.
Each later plan starts only after its predecessor is merged to `master`. No later
batch starts from an unmerged earlier batch.

The mandatory order is:

```text
deep current-system diagnosis
  -> deep external primary-source research
  -> measured experiments and decision records
  -> approved detailed target architecture / migration / evaluation specs
  -> TDD implementation
  -> measured release gates
```

Program 1 must produce and obtain approval for the final implementation
specifications before substantial production implementation begins. No metric may
become a release gate until its ground-truth labeling method is defined.

## 2. Why The Previous Three-Part Plan Was Rejected

The previous split organized work as:

1. retrieval/provenance;
2. math extraction;
3. graph/community/quota.

That sequencing is invalid:

- compiler/math changes alter source spans, chunks, embeddings, and retrieval
  rankings after retrieval was declared stable;
- entity resolution and communities change the compiled corpus and global search
  after earlier retrieval baselines;
- quota and circular storage UI do not establish RAG/DAG correctness;
- component-level success can hide end-to-end loss of evidence.

The revised split follows end-to-end correctness boundaries:

1. **Truth Contract & Quality Observatory**
2. **Evidence Compiler Integrity**
3. **Agentic Query Serving & Sensemaking**

## 3. Vault-As-Codebase Model

The analogy guides interfaces and evaluation without forcing notes into a code
schema.

| Codebase concept | Notes-vault knowledge concept |
|---|---|
| repository | vault + external Reference Mode sources |
| module/file | note, PDF, promoted Wiki artifact, external source |
| symbol/address | heading, block id, page, section, citation, semantic unit |
| import/reference | wikilink, embed, backlink, frontmatter ref, citation |
| semantic IR | claims, definitions, decisions, procedures, questions, examples, equations, contradictions |
| dependency graph | authored links + extracted relations + derivation dependencies |
| compiler | source → spans → knowledge IR → graph/hierarchy → indexes |
| language server / code search | context manifest, retrieval, traversal, provenance expansion |
| build cache | derived search rows, embeddings, projections, reports, synthesis |
| test suite | frozen vault tasks, qrels, claim support, agent task success |
| git/file version | source hash, corpus snapshot, dependency/search epoch |

Authored topology and extracted topology must remain distinguishable. A human
wikilink is not equivalent to an LLM-inferred relation, and a semantic similarity
is not equivalent to either.

## 4. Current-System Verdict

Incurator already has credible foundations:

- DB-native hybrid retrieval;
- L1 source spans and L2-L4 generated records;
- prompt/query traces and artifact dependencies;
- source-truth/derived-insight/human-promotion separation;
- MCP and plugin query surfaces.

However, the parts are not yet composed into one trustworthy compiler and one
reproducible context-serving transaction.

Verified high-priority defects and stable Failure Atlas IDs include:

1. **F1:** search-hit `source_span_ids` are dropped during evidence assembly;
2. **F2:** a single query can create disconnected retrieval/orchestrator traces;
3. **F3:** KRS/`curate.yml` policy is not enforced through all evidence routes;
4. **F4:** global evidence is effectively query-independent and source-scoped evidence
   can be unbounded;
5. **F5:** context packing uses a fixed character cutoff, not explicit token budgets or
   progressive disclosure;
6. **F6:** broad upstream span fallback can make unsupported generated claims appear
   grounded;
7. **F7:** rebuild idempotency, atomicity, stale-record reconciliation, and dependency
   hashes are not proven;
8. **F8:** exact-name entity merging and connected-component communities are fragile;
9. **F9:** authored note structure is not fully compiled as high-confidence semantic
   topology;
10. **F10:** searchable source evidence is often limited to a short preview;
11. **F11:** explore is not yet a measured iterative research loop;
12. **F12:** external and Obsidian agents do not share one context contract;
13. **F13:** the active testbed does not measure the current architecture's truth,
    retrieval, agent reuse, or incremental correctness.

Full diagnosis plan: `.agents/plans/D_current_system_failure_atlas.md`.

## 5. External Research Strategy

Do not replace Incurator wholesale with GraphRAG, LightRAG, HippoRAG, RAPTOR, or
another framework. Incurator already combines many of their ideas and has a
stronger provenance-first constraint.

Benchmark isolated candidate techniques against reproduced failures:

- deterministic context-enriched chunks;
- HippoRAG-style passage/entity graph + Personalized PageRank;
- denoised hierarchical communities;
- query-relevant community selection and GraphRAG/DRIFT-like exploration;
- KG2RAG-style graph-guided chunk expansion and organization;
- CRAG-style retrieval sufficiency/corrective gate;
- Adaptive-RAG-style complexity routing;
- bounded iterative retrieval inspired by RepoCoder/agentic retrieval;
- conditional formula recovery only where parser loss is measured.

Reject:

- graph-only retrieval;
- automatic semantic entity merging;
- eager summarization without staleness/cost evidence;
- fixed top-k for every task;
- model-judge-only release gates;
- count-based quality claims.

Research seed and primary sources:
`.agents/plans/E_external_research_design_matrix.md`.

## 6. Required Program-1 Specification Package

Before Program 1 production coding, author and approve these full documents using
the repository planning/spec workflow:

1. **Failure Atlas**
   - Reproduced failures mapped to the exact loss/corruption boundary.
   - Every concern classified as reproduced, disproven, accepted, or scheduled.
2. **External Design Matrix**
   - Candidate techniques compared by quality, cost, latency, update behavior,
     provenance, dependency risk, and failure mode.
3. **Evaluation Specification**
   - Datasets/scenarios, qrels, claim labels, holdout partitions, human-review
     sampling, metrics, latency/token environment, and pass/fail thresholds.
4. **Target Knowledge IR & Compiler Specification**
   - Semantic unit types, authored/extracted edges, stable identities, lineage,
     truth/freshness lifecycle, reconciliation, invalidation, migrations.
5. **Target Query Transaction & Context Service Specification**
   - One QTR transaction, route policies, evidence-pack schema, token budgets,
     snapshots, progressive expansion, feedback lineage, cross-client parity.
6. **Migration And Rollback Specification**
   - Current schema reality, additive migration, rebuild policy, DB backup,
     compatibility/removal decisions, rollback points.

The static specs and English/Korean guides are updated from those approved
documents before behavior implementation.

## 7. Shared Quality Model

### 7.1 Ground-truth layers

- deterministic expected record/span ids where possible;
- claim-to-minimal-support labels;
- route/task labels;
- hard negatives and contradiction fixtures;
- sampled human review for semantic judgments;
- calibrated model judges only as secondary metrics.

### 7.2 Required metric families

**Compiler**

- claim support correctness/completeness;
- stale/duplicate record rate;
- exact rebuild idempotency;
- dependency-closure invalidation precision/recall;
- central formula and authored-link preservation;
- entity duplicate/false-merge rate;
- unsupported relation rate;
- community stability and giant-component ratio.

**Retrieval**

- Recall@1/3/5, MRR, nDCG@10;
- hard-negative outrank count;
- expected source-span and multi-hop path recall;
- route selection accuracy;
- context precision/recall per token;
- degraded-mode frequency.

**Answer and agent task**

- claim-level citation correctness and completeness;
- unsupported-claim and contradiction rate;
- exact locator resolution;
- external/Obsidian context parity;
- end-to-end task success;
- p50/p95 latency, token usage, and model cost.

Report per query/task family. Aggregate-only claims are prohibited.

## 8. Program 1 — Truth Contract & Quality Observatory

### Objective

Make every system claim, compiled artifact, and agent answer measurable,
auditable, and reproducible before changing major compiler or retrieval
algorithms.

### Explicit non-goals

- no reranker/RRF weight tuning;
- no guaranteed VLM formula pipeline;
- no Leiden/community replacement;
- no entity auto-merge;
- no quota UI or Convert-to-LaTeX settings work.

### P1.0 — Research Branch And Evidence Ledger

- Finish/merge or conclude current Claude/user work.
- Handle or explicitly override higher-priority ROADMAP bugs.
- Start Plan D1 on a fresh Program-1 branch from `master`; after D1 merges, start
  Plan E on its own fresh Program-1 research branch; after E merges, start Plan
  D2 on a fresh Program-1 observatory branch; update `RELAY.md`.
- Select/confirm active testbed scenarios.
- Record exact SHA, schema, providers, model files, testbed DB state, and rollback
  anchor.

Verify: no production behavior changes; baseline environment is reproducible.

### P1.1 — Deep Failure Reproduction

- Execute the approved `D_current_system_failure_atlas.md` plan.
- Execute every experiment in the Failure Atlas.
- Trace representative claims end to end.
- Test edit/delete/rename/split, failed batch, unchanged rebuild, source drift,
  policy changes, missing providers, and cross-client requests.
- Record current baseline metrics and exact command outputs.

Verify: each known defect has a minimal fixture and a pipeline-boundary diagnosis.

### P1.2 — External Research And Comparative Spikes

- Execute the approved `E_external_research_design_matrix.md` plan.
- Deepen the primary-source research matrix.
- Build small disposable prototypes/benchmarks where a paper's claimed benefit is
  relevant but uncertain.
- Compare current behavior to contextual chunks, PPR, hierarchical communities,
  dynamic community selection, graph-guided expansion, and bounded iteration.
- Record ADR-style adopt/benchmark/reject decisions.

Verify: no technique is approved without a reproduced target failure and measured
comparison.

### P1.3 — Final Detailed Specifications

- Author the six-document package in §6.
- Update all affected static specs synchronously.
- Define exact schema/API migrations and removal of stale qmd/EXH assumptions.
- Obtain user approval before implementation.

Verify: every implementation phase has a contract, test oracle, and rollback.

### P1.4 — Quality Observatory Implementation

After approval, implement only the substrate needed to make later work safe:

- one authoritative end-to-end query transaction and trace;
- claim/source/corpus/config/model identities needed for reproducibility;
- structured source locators and exact evidence lineage;
- permanent evaluation runner and frozen holdout partitions;
- current-architecture testbed scenarios;
- cross-client normalized trace/evidence inspection;
- critical provenance-adapter repairs required for valid measurement.

### Program 1 Release Gates

- Plan D1 is merged and its baseline/oracle handoff passes;
- Plan E research decision package is approved and merged;
- Plan D2 is merged after the §6 final target specification package incorporates
  D1 and E and the approved minimum Quality Observatory is implemented;
- exactly one authoritative QTR per query surface;
- 100% selected source-supported evidence has resolvable record and source ids;
- 0 fabricated working-looking links;
- deterministic repeatability under unchanged corpus/config/model;
- citation correctness at least 95% and completeness at least 90% on the initial
  gold suite, or user-approved revised thresholds backed by measured baseline;
- every query/task family has a holdout;
- all known failures reproducibly classified;
- full local CI and Program 1 testbed pass.

Program 2 starts only from merged Program 1 `master`.

## 9. Program 2 — Evidence Compiler Integrity

### Objective

Make note/PDF → L1-L4 compilation faithful, deterministic, atomic,
incrementally maintainable, and claim-level source-grounded. This program defines
what reusable prior knowledge exists.

### Focused research before implementation

- evaluate note-native semantic IR designs and authored-link preservation;
- fact-check formula loss at parser, L1, L2, graph, report, synthesis, and search
  boundaries;
- evaluate entity resolution/alias strategies and graph extraction fidelity;
- benchmark hierarchy/community methods only after graph denoising;
- measure rebuild/staleness/dependency failures.

### P2.0 — Program 2 Implementation Specification

Using Program 1 evidence, freeze:

- Knowledge IR schema and truth/freshness lifecycle;
- authored vs extracted edge contracts;
- stable semantic identity/reconciliation algorithm;
- transactional compile/rebuild/invalidation behavior;
- formula/citation/code-aware evidence rules;
- entity alias/merge and relation-support lifecycle;
- hierarchy/community and synthesis invalidation policy;
- migration and rollback.

Update static specs/guides before code and stop for approval.

Program 2 implementation follows the approved
`B_math_extraction_distillation.md` and `C_graph_quality.md` component plans.

### P2.1 — Source And Note-Native IR

- Preserve file, heading, block, page, section, citation, and external-reference
  locators.
- Compile authored wikilinks, embeds, backlinks, aliases, tags, frontmatter refs,
  and citations as distinct high-confidence topology.
- Preserve exact raw evidence while permitting derived contextual search material.
- Make long-source searchable evidence retrievable without treating a 200-character
  preview as sufficient source truth.

### P2.2 — Stable Identity, Atomicity, And Reconciliation

- Define stable identities for semantic units and generated artifacts.
- Compile a source transactionally; failed batches do not leave partial truth.
- Reconcile changed/deleted units, entities, relations, reports, synthesis, search
  rows, dependencies, and projections.
- Make unchanged rebuilds authoritative-record-idempotent.
- Regenerate only the measured dependency closure after a source change.

### P2.3 — Claim-Level Knowledge Extraction And Math Integrity

- Extract note-native semantic unit types under prompt contracts.
- Require minimal supporting spans for each generated claim.
- Remove broad "all upstream spans" grounding fallback.
- Add selective formula recovery only where Program 1 proves parser loss.
- Preserve central formulas, code, citations, and contradictions; record explicit
  provisional/unsupported states rather than inventing support.

### P2.4 — Graph Resolution And Knowledge Hierarchy

- Add reversible aliases/merge proposals and strict homonym protection.
- Aggregate independent relation support; quarantine unsupported/noisy edges.
- Benchmark and implement a deterministic weighted hierarchy when it improves
  compiler/query metrics; Leiden is a candidate, not the goal.
- Generate reports/synthesis with claim-level evidence and exact dependency hashes.

### P2.5 — Compiler Audit And Current Testbed

- Rewrite stale EXH/qmd scenarios around current DB-native architecture.
- Add a compiler audit that traverses every L2-L4 claim to minimal source support.
- Add adversarial note, PDF, formula, synonym/homonym, contradiction, and update/
  delete fixtures.

### Program 2 Release Gates

- 100% fixed gold claims have at least one minimal supporting span;
- 0 broad all-upstream-span grounding fallbacks;
- unchanged rebuild produces identical authoritative records/dependency hashes;
- one-source edit regenerates only the expected dependency closure;
- failed compile produces no partial authoritative state;
- 0 homonym false merges in adversarial fixtures;
- every relation is directly supported or explicitly provisional/quarantined;
- central-formula recall meets the approved gold threshold with 0 silent
  hallucinated replacement;
- hierarchy is seed-stable and has no unexplained giant component;
- full compiler audit and local CI pass.

Program 3 starts only from merged Program 2 `master`.

## 10. Program 3 — Agentic Query Serving & Sensemaking

### Objective

Serve trusted compiled prior knowledge to external and Obsidian agents through
one bounded, progressive, freshness-aware runtime, then optimize hybrid RAG+DAG
retrieval against the frozen quality suite.

Target contract seed:
`.agents/plans/F_agent_context_service.md`.

### Focused research before implementation

- benchmark contextual chunks against current chunks;
- benchmark current depth-two memory paths against passage/entity PPR;
- benchmark selected-community local/global/DRIFT-style flows;
- benchmark graph-guided chunk expansion and organization;
- benchmark sufficiency-gated bounded iterative retrieval;
- measure direct factual, associative, global, source-scoped, and agent task
  quality separately.

### P3.0 — Program 3 Implementation Specification

Freeze:

- one backend `ContextService`;
- context manifest/fetch/expand/verify/feedback operations;
- evidence-pack and snapshot schema;
- route-specific evidence policy;
- token/context budget and progressive-disclosure rules;
- adaptive/corrective/iterative stop rules;
- feedback and promotion lineage;
- MCP/plugin/CLI parity and migration.

Update static specs/guides before code and stop for approval.

Program 3 implementation follows the approved
`A_rag_retrieval_provenance.md` and `F_agent_context_service.md` component plans.

### P3.1 — Unified Context Service

- Make `curator_query`, `curator_fetch_context`, raw search, plugin JSON, and
  Obsidian grounding delegate to one service.
- External and Obsidian agents receive equivalent normalized packs.
- Backend answer synthesis consumes the same pack and remains optional.
- Enforce KRS policy, source scope, truth/freshness rules, and explicit
  degradation on every route.

### P3.2 — Progressive Context And Reproducible Snapshots

- Add manifest → index → excerpt → exact source expansion.
- Enforce model-aware token budgets, per-item limits, reserved expansion budget,
  explicit omissions, and expansion handles.
- Attach DB/search/policy epochs and reject stale mixed-snapshot expansion.
- Render exact evidence/locators used for reasoning in Sources & Trace.

### P3.3 — Measured Hybrid RAG+DAG Serving

- Keep lexical/vector/RRF/rerank as the factual/local baseline.
- Add context-enriched chunks if they win the benchmark.
- Add graph-guided expansion/PPR only where associative/multi-hop metrics improve
  without factual regression.
- Select query-relevant communities/synthesis for global queries.
- Add bounded DRIFT/iterative retrieval only behind complexity/sufficiency gates.
- Tune weights/models/routes only against frozen Program 1/2 holdouts.

### P3.4 — Agent Feedback And Prior-Knowledge Reuse Loop

- Preserve trace/snapshot/evidence lineage for relevant, irrelevant, incorrect,
  stale, insufficient, duplicate, new-insight, correction, and promotion events.
- Corrections remain source-truth-safe and review-gated.
- Promotions record their origin and become explicit human-verified prior
  knowledge.
- Evaluate whether feedback improves later retrieval without silently biasing
  truth.

### P3.5 — Operational Quality And Cross-Client UX

- Expose route, budget, freshness, omissions, degradation, trace, and exact
  evidence navigation.
- Validate note, heading, block, PDF page, and external-reference links.
- Measure full-quality and degraded-mode latency/token budgets separately.

### Program 3 Release Gates

- no query-family Recall@5 or nDCG@10 regression above approved tolerance;
- targeted failing families improve by the approved minimum;
- global/source routes are bounded and query-relevant;
- direct factual quality is not sacrificed by graph/agentic retrieval;
- citation correctness/completeness meet approved thresholds;
- unsupported-answer and hard-negative rates do not regress;
- external MCP and Obsidian normalized packs are equivalent;
- every route passes token-budget, snapshot, provenance, locator, and degraded-mode
  fixtures;
- end-to-end agent task suite, local CI, and testbed pass.

## 11. Scope Exclusions And Follow-Up Milestones

The following do not block RAG/DAG stabilization and must not expand this program:

- vault quota limit, circular storage UI, and storage admission control;
- Convert-to-LaTeX provider settings and unrelated light-model UI;
- native PDF annotation system;
- web search as an unlabeled substitute for missing vault evidence;
- automatic edits to `03_Notes/`, `04_Resources/`, or `06_Archives/`.

Program 1 may measure storage growth, provider needs, and web/corpus gaps, then
queue separate milestones.

## 12. Shared Execution Discipline

Every program:

1. starts from merged `master` on its own branch;
2. executes only its approved A-F component Master Plans and creates a fresh
   evidence ledger against the implementation branch;
3. performs focused research and updates specs/guides before code;
4. stops for user approval;
5. follows TDD and incremental commits;
6. runs roles sequentially:
   `coder_engineer` → `peer_reviewer` → `schema_guardian` →
   `source_pair_analyst` → `qa_runner` → `docs_sync_manager` →
   `legacy_sweeper`;
7. runs full local CI and active testbed;
8. performs mandatory version/changelog/release commit/push/PR;
9. stops until merged before the next program.

Local CI:

```bash
export UV_PROJECT_ENVIRONMENT="$(git rev-parse --show-toplevel)/.venv"
uv run --directory backend pytest -q
uv run --directory backend ruff check src/
uv run --directory backend mypy src/
npx vitest run -c ./plugin/vitest.config.ts
```

## 13. Required Documentation Surfaces

Update relevant current static specs synchronously:

- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`
- `docs/specs/curator_schema/SCHEMA.md`
- `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`
- search-specific schema/contract docs where applicable

Update English guides first, then faithful `_KR.md` counterparts:

- `USER_GUIDE`
- `WORKFLOW_GUIDE`
- `MCP_USER_GUIDE`
- `AGENT_WORKFLOW_GUIDE`
- `PLUGIN_GUIDE`

## 14. Stop Conditions

- Stop now: planning may be refined and committed on the current PR branch, but
  implementation is blocked until that PR is merged and the relevant component
  plans are approved.
- Stop Program 1 implementation until the §6 specification package is approved.
- Stop any technique adoption without a reproduced target failure and benchmark.
- Stop Program 2 if claim support, idempotency, or atomicity cannot be measured.
- Stop Program 3 if the trusted Program 2 compiler substrate is not merged.
- Stop graph/agentic retrieval if it improves associative/global tasks by
  sacrificing factual quality beyond tolerance.
- After three repeated QA failures, activate `rollback_strategist`, restore the
  last stable release state, and return to planning.

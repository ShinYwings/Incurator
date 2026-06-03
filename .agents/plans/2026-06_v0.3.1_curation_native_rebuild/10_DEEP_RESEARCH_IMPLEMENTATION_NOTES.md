# Deep Research Implementation Notes

## 1. Purpose

The earlier research plan captured the broad architectural lessons, but it did
not go far enough into implementation mechanics. This document translates
external RAG systems into concrete engineering implications for the current
Incurator codebase.

The goal is not to copy another system. The goal is to understand the internal
shape of those systems deeply enough to decide exactly what Incurator should
build, reject, or adapt.

Primary references reviewed for this revision:

- Microsoft GraphRAG official indexing overview:
  <https://microsoft.github.io/graphrag/index/overview/>
- Microsoft GraphRAG indexing architecture:
  <https://microsoft.github.io/graphrag/index/architecture/>
- Microsoft GraphRAG output schema:
  <https://microsoft.github.io/graphrag/index/outputs/>
- Microsoft GraphRAG query overview:
  <https://microsoft.github.io/graphrag/query/overview/>
- Microsoft GraphRAG prompt tuning:
  <https://microsoft.github.io/graphrag/prompt_tuning/overview/>
- LightRAG arXiv:
  <https://arxiv.org/abs/2410.05779>
- HippoRAG arXiv:
  <https://arxiv.org/abs/2405.14831>
- HippoRAG 2 arXiv:
  <https://arxiv.org/abs/2502.14802>
- RAPTOR arXiv:
  <https://arxiv.org/abs/2401.18059>
- LlamaIndex Property Graph Index docs:
  <https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/>
- Cursor secure codebase indexing:
  <https://cursor.com/blog/secure-codebase-indexing>

## 2. What The External Systems Actually Implement

### 2.1 Microsoft GraphRAG

Microsoft GraphRAG is not merely "vector search with a graph." Its official
indexing architecture is a pipeline of workflows:

```text
LoadDocuments
  -> ChunkDocuments
  -> ExtractGraph
  -> ExtractClaims
  -> EmbedChunks
ExtractGraph
  -> DetectCommunities
  -> EmbedEntities
DetectCommunities
  -> GenerateReports
GenerateReports
  -> EmbedReports
```

The key implementation decision is that the query layer operates on a completed
knowledge model. The query engine is downstream of indexed graph artifacts,
community artifacts, text units, and embeddings.

GraphRAG's default output tables include:

- `documents`
- `text_units`
- `entities`
- `relationships`
- `communities`
- `community_reports`
- optional `covariates` such as extracted claims

The community/report representation is especially relevant:

- communities are hierarchical;
- communities carry entity ids, relationship ids, and text-unit ids;
- community reports have title, summary, full content, rank, rating
  explanation, findings, and JSON content;
- community rows include `period` and `size` fields to support incremental
  update merges.

GraphRAG's query implementation is explicitly mode-separated:

- Local Search combines graph data with raw text chunks for entity-specific
  questions.
- Global Search searches over community reports and uses map-reduce synthesis.
- DRIFT starts from community context, expands into follow-up questions, and
  refines with local search.
- Basic Search remains as a baseline vector/top-k comparison path.
- Question Generation produces follow-up investigative questions.

GraphRAG also treats prompt tuning as a first-class subsystem. It exposes
default prompts, auto tuning, and manual tuning instead of scattering prompt
strings invisibly through the code.

#### Incurator Implementation Implications

Current Incurator equivalents:

| GraphRAG concept | Current Incurator location | v0.3.1 implementation implication |
| --- | --- | --- |
| documents | `sources` table in `backend/src/curator/db.py` | Keep `sources`, but add durable source-span rows and artifact dependency rows. |
| text_units | no first-class table; qmd chunks are external | Add `source_spans` and `knowledge_units`; do not rely only on qmd chunks. |
| entities | absent except L2/L3 page text | Add `graph_entities` table and entity extraction prompt family. |
| relationships | `dag_edges` only models CTX/ATM/CON/EXH lineage | Add `graph_relations` for semantic relations; keep `dag_edges` for compiler lineage. |
| communities | absent | Add `graph_communities` or encode community id on `community_reports`. |
| community_reports | absent | Add `community_reports` as generated L3-adjacent artifacts. |
| claim covariates | partially L2 Atoms | Add typed `knowledge_units` with claim/equation/procedure/definition classes. |
| prompt tuning | `prompts.py` string constants | Add prompt registry, prompt contracts, prompt trace, prompt evals. |
| local/global/DRIFT | `query.py` single qmd search path | Add retrieval router and route-specific evidence builders. |

The most important design adaptation:

GraphRAG's `community_reports` should not become Incurator's L4. Incurator's L4
is Exhibition. Community reports are reusable graph-level summaries; Exhibitions
are workspace-specific context packages staged from `curate.yml`.

### 2.2 LightRAG

LightRAG's paper frames the problem as a failure of flat data representations.
Its implementation direction is graph structures plus vector representations,
with dual-level retrieval over low-level and high-level knowledge. The paper
also emphasizes incremental update so new data can be integrated without
rebuilding the full system.

The implementation idea to borrow is not "install LightRAG." The idea is that
a changing knowledge base needs:

- graph records that can be updated locally;
- vector records that can be updated locally;
- a retrieval strategy that can combine low-level evidence and high-level
  context;
- incremental merge logic.

#### Incurator Implementation Implications

Current Incurator already has a better identity model than LightRAG:

- source truth;
- human-promoted knowledge;
- Exhibition staging;
- backprop;
- Obsidian workspace behavior.

But current Incurator has weaker low/high retrieval composition:

- `search.query()` returns qmd hits.
- `query.run_query()` hydrates those hits and writes one synthesis prompt.
- `curate_yml.CurateSpec.boost_query()` appends persona/domain terms to the
  search text.

v0.3.1 should split retrieval into a composable set of retrievers:

```text
SourceSpanRetriever
KnowledgeUnitRetriever
EntityRelationRetriever
CommunityReportRetriever
MemoryPathRetriever
ExhibitionRetriever
QmdFallbackRetriever
```

Each retriever should return a shared `EvidenceItem` structure instead of raw
`SearchHit`.

### 2.3 HippoRAG / HippoRAG 2

HippoRAG uses knowledge graphs and Personalized PageRank to emulate associative
long-term memory. HippoRAG 2 explicitly builds on that with deeper passage
integration and more effective online LLM usage, improving factual,
sense-making, and associative memory tasks.

The implementation lesson is that related knowledge is not always retrieved by
nearest-neighbor similarity. A query can activate an entity or concept, then
walk a graph to related memory. This is especially relevant for note-writing:
the agent often needs "what prior note does this remind me of?" rather than
"what chunk has the same words?"

#### Incurator Implementation Implications

Current Incurator has graph lineage edges:

```text
CTX -> ATM
ATM -> CON
CON -> EXH
```

Those edges are not enough for associative memory. v0.3.1 needs separate
semantic graph edges:

```text
entity -> entity
entity -> claim
claim -> concept
concept -> source_span
concept -> exhibition
insight_candidate -> concept
```

The implementation should not require a heavy graph database initially.
SQLite is enough for v0.3.1 if the tables are explicit:

```text
graph_entities(id, canonical_name, type, description, ...)
graph_relations(id, source_entity_id, target_entity_id, relation_type, ...)
memory_paths(id, query_hash, start_node_id, path_json, score, ...)
```

The retrieval algorithm can begin with a deterministic approximation:

1. Retrieve seed entities from `graph_entities` using lexical/qmd/vector search.
2. Expand one or two hops through `graph_relations`.
3. Score by relation confidence, source-span support, and `curate.yml`
   constraints.
4. Store the chosen path in `memory_paths` and query trace.

Personalized PageRank can be added later. The first implementation should
preserve the path trace and source spans; that is more important than algorithm
purity.

### 2.4 RAPTOR

RAPTOR recursively embeds, clusters, and summarizes chunks into a tree. At
query time it retrieves across the tree so the model can use both detailed and
abstract context.

Its strength is abstraction-level retrieval. Its weakness for Incurator is that
trees are too rigid for cross-document notes. A note vault is not a single
document hierarchy; it is a graph of claims, sources, concepts, projects, and
human insights.

#### Incurator Implementation Implications

Use RAPTOR inside the graph, not as the graph:

- For long PDFs, generate section-level and document-level source summaries.
- For large communities, generate community reports from grouped units.
- Store summary artifacts with dependency edges to their source spans.
- Invalidate summaries upward when a source span changes.

Do not replace `02_Atoms` and `03_Concepts` with a recursive summary tree.
Atoms and Concepts are human-inspectable latent-space nodes, not just retrieval
optimization artifacts.

### 2.5 LlamaIndex Property Graph

LlamaIndex Property Graph Index shows a modular design:

- extractors create graph nodes and relations;
- a property graph store owns graph data;
- sub-retrievers such as vector context and synonym retrievers compose under a
  `PGRetriever`;
- relation traversal depth is configurable.

The implementation lesson is modularity, not dependency adoption.

#### Incurator Implementation Implications

v0.3.1 should create Incurator-owned abstractions:

```python
class ExtractorProtocol(Protocol):
    prompt_id: str
    output_model: type[BaseModel]
    def build_messages(...) -> list[ChatMessage]: ...
    def validate(...) -> ValidationResult: ...

class RetrieverProtocol(Protocol):
    route: RetrievalRoute
    def retrieve(query: QueryRequest, ctx: RetrievalContext) -> EvidencePack: ...
```

Do not wrap the whole system in LlamaIndex because Incurator needs source truth,
Reference Mode, Exhibition, and backprop semantics that are project-specific.

### 2.6 Cursor Codebase Indexing

Cursor's implementation lesson is strong:

- a Merkle tree over files and directories;
- SHA-256 hashes;
- syntactic chunks;
- embeddings generated asynchronously;
- embedding cache keyed by chunk content;
- index reuse when chunks remain unchanged.

This maps directly to Incurator because a vault changes constantly.

#### Incurator Implementation Implications

Current Incurator tracks `sources.content_hash` and `page_hashes`, but v0.3.1
needs a finer invalidation model:

```text
source file hash
  -> source span hash
  -> knowledge unit hash
  -> entity/relation hash
  -> community report dependency hash
  -> Exhibition dependency hash
```

Implementation should add `artifact_dependencies`:

```text
artifact_dependencies(
  artifact_id,
  artifact_type,
  depends_on_id,
  depends_on_type,
  dependency_hash,
  created_at
)
```

Then query/exhibition/report caches can be invalidated by dependency graph
instead of broad full rebuild.

## 3. Current Incurator Code-Level Diagnosis

### 3.1 Prompt System Diagnosis

Current files:

- `backend/src/curator/prompts.py`
- `backend/src/curator/query.py`
- `backend/src/curator/backprop_agents.py`
- `backend/src/curator/contradiction.py`
- `plugin/src/context/systemPrompt.ts`
- persona prompt snippets inside `backend/src/curator/cli.py` and
  `backend/src/curator/mcp_server.py`

Current issues:

- prompt strings and prompt builders live in one very large `prompts.py`;
- prompt ids and versions are not recorded at runtime;
- output schemas exist as Pydantic models in `ingest_llm.py`, but the prompt
  contract does not explicitly point to the output model;
- retry behavior is hand-coded per call;
- prompt trace is not stored in SQLite;
- plugin prompt guidance is separate from backend prompt contracts;
- query synthesis prompt is defined inside `query.py`, not the prompt subsystem;
- current system prompt forces generated DAG output to English, which is useful
  for stable indexing but must be distinguished from response-language behavior
  and workspace note-writing behavior.

Required v0.3.1 change:

`prompts.py` should become a compatibility wrapper, not the main owner.

### 3.2 Query/Orchestration Diagnosis

Current files:

- `backend/src/curator/query.py`
- `backend/src/curator/search.py`
- `backend/src/curator/plugin_api.py`
- `backend/src/curator/mcp_server.py`

Current query behavior:

1. translate or receive English working query;
2. optionally classify intent;
3. call `search.query()` against qmd;
4. apply post-hoc layer filtering;
5. sort L4 Exhibitions first;
6. build one synthesis prompt;
7. stream answer;
8. optionally save as query-generated Exhibition.

Current issues:

- no explicit retrieval route object;
- no `EvidencePack`;
- no global/community report mode;
- no DRIFT/explore mode;
- no graph path/memory path mode;
- no prompt trace;
- trace returned to plugin/MCP is shallow;
- `curate.yml` contributes mostly boost terms and pinned Exhibition.

Required v0.3.1 change:

`query.run_query()` should become a wrapper around a new query orchestrator.
The orchestrator chooses route, builds evidence pack, runs prompt contract, and
records trace.

### 3.3 Database Diagnosis

Current `backend/src/curator/db.py` has:

- `sources`
- `source_pdf_pages`
- `ingest_runs`
- `source_pages`
- `ingest_jobs`
- `job_events`
- `atoms`
- `concepts`
- `synthesis`
- `page_hashes`
- `dag_edges`

This is enough for v0.2.x source/DAG operations, but not enough for v0.3.1.

Missing:

- source spans for markdown/PDF/math location;
- typed knowledge units independent of markdown page text;
- entity records;
- relation records;
- community report records;
- memory path records;
- prompt run traces;
- curation plan records;
- insight candidates;
- artifact dependency edges.

Required v0.3.1 change:

Add these tables through an idempotent migration while preserving existing
markdown artifacts and existing v0.2.x tables.

### 3.4 `curate.yml` Diagnosis

Current `backend/src/curator/curate_yml.py` parses:

- project;
- description;
- vault_root;
- sources include/exclude;
- min_confidence;
- exhibition;
- persona domain/subdomain/goal/intent/disambiguation/confidence.

Current issues:

- `CurateSpec` does not model source policy, output contract, reasoning modes,
  verification policy, contradiction policy, backprop policy, prompt profile, or
  exploration settings as first-class dataclasses;
- `boost_query()` is too small relative to the intended Knowledge Requirement
  Specification role;
- validation is shallow;
- there is no compiled form of `curate.yml` that the query orchestrator can use.

Required v0.3.1 change:

Add `compile_curate_spec(spec) -> CurationPolicy` and make route selection,
prompt profile selection, verification, and source filtering consume that
compiled policy.

### 3.5 Ingest Diagnosis

Current `backend/src/curator/ingest_llm.py` has:

- `SummaryData`
- `AtomCandidate`
- `ConceptPlan`
- `SynthesisPlan`
- L2/L3/L4 page drafting;
- embedding-clustering fallback;
- DAG edge recording.

Current issues:

- L1 source map is markdown/frontmatter centric, not span centric;
- `AtomCandidate` has no mandatory source span id;
- concept/entity/relation extraction is not separate;
- community reports are absent;
- prompt traces are absent;
- generated artifacts cannot be invalidated by source-span dependency.

Required v0.3.1 change:

Keep L1-L4 page writing, but insert structured records before/alongside pages:

```text
parsed source -> source_spans
source_spans -> knowledge_units
knowledge_units -> entities/relations
entities/relations -> community_reports
community_reports + concepts + curate.yml -> Exhibition
```

### 3.6 Interface Diagnosis

Current backend local plugin API:

- `plugin source status/import/register/rebind`
- `plugin pdf context/search`
- `plugin query`
- `plugin promote`
- Zotero commands

Current MCP server:

- `curator_query`
- `promote_exhibition`
- `curator_curate_workspace`
- `curator_check_workspace`
- `curator_workspace_init`
- `curator_get_node`
- `curator_traverse_evidence`
- layer/status/add/build/sync/lint/reindex/backprop helpers

Current plugin UI:

- `plugin/src/ui/incuratorQueryTrace.ts` renders a shallow trace panel;
- `plugin/src/agent/incuratorClient.ts` shells out to hidden backend commands.

Required v0.3.1 change:

Add trace-rich payloads through shared backend services. MCP and plugin commands
should call the same functions, not duplicate query/cache/promotion logic.

## 4. Deep Design Decisions

### 4.1 Community Reports Are Not Exhibitions

Implementation rule:

- `community_reports` are reusable graph summaries.
- `Exhibitions` are workspace-specific context packages.
- A workspace Exhibition may cite community reports, but it must also cite
  source spans and comply with `curate.yml`.

Concrete schema implication:

```text
community_reports.id != EXH-id
community_reports.report_id should use REP- prefix or SQL id
Exhibition frontmatter may contain community_report_ids: [...]
```

### 4.2 Memory Paths Are Query Trace Artifacts First

Implementation rule:

- `memory_paths` should first record why the system retrieved something.
- They can later become reusable cache records.
- Do not optimize PageRank before trace fidelity exists.

Concrete schema implication:

```text
memory_paths.path_json contains ordered nodes:
[
  {"id": "ENT-...", "type": "entity", "why": "..."},
  {"id": "REL-...", "type": "relation", "why": "..."},
  {"id": "CON-...", "type": "concept", "why": "..."}
]
```

### 4.3 Prompt Contracts Must Own Output Validation

Implementation rule:

- Pydantic models should move close to prompt contracts or be imported by them.
- Every prompt family must declare input schema, output schema, validators, and
  trace fields.
- Retry prompts should be generated by the contract, not hand-written per call.

Concrete schema implication:

```text
prompt_runs(
  trace_id,
  prompt_id,
  prompt_version,
  input_hash,
  output_hash,
  validator_status,
  validator_errors,
  model_provider,
  model_name
)
```

### 4.4 Source Truth Must Be A Type System Rule

Implementation rule:

- Every generated claim must have either source-span provenance or be explicitly
  classified as derived insight.
- Derived insight cannot be written into L1 source context.
- Backprop patch planning must classify before updating.

Concrete schema implication:

```text
knowledge_units.truth_status:
  source_supported
  derived_insight
  contradiction
  promoted_human_truth
```

### 4.5 `curate.yml` Should Compile Into Runtime Policy

Implementation rule:

Do not pass raw `CurateSpec` everywhere. Add a compiled runtime policy:

```python
@dataclass
class CurationPolicy:
    workspace_id: str
    project: str
    source_include: list[str]
    source_exclude: list[str]
    allowed_routes: set[RetrievalRoute]
    default_route: RetrievalRoute
    prompt_profile: str
    require_source_spans: bool
    allow_general_knowledge: bool
    contradiction_policy: str
    backprop_policy: str
    max_explore_followups: int
```

This gives `query.py`, prompt builders, community report generation, and
backprop the same interpretation of the workspace spec.

## 5. Implementation Priority Derived From Research

The code should not start with graph algorithms. It should start with contracts.

1. Add prompt registry/contracts/traces.
2. Add source spans and artifact dependencies.
3. Add compiled `CurationPolicy`.
4. Add `EvidenceItem` and `EvidencePack`.
5. Split `query.run_query()` into route-specific orchestration.
6. Add typed knowledge units/entities/relations.
7. Add community reports.
8. Add memory paths.
9. Add insight lifecycle/backprop classifier.
10. Expand CLI/MCP/plugin payloads.

This order prevents the project from building graph features that cannot be
traced, tested, or governed by `curate.yml`.

## 6. Rejected Paths After Deep Research

Reject these implementation shortcuts:

- Replacing qmd with GraphRAG wholesale.
- Adding a second `.curator/notebase/` product directory.
- Using LlamaIndex as the main runtime abstraction.
- Treating community reports as L4.
- Treating memory paths as truth.
- Allowing query-generated insights to update L1.
- Adding prompt strings without ids/versions/contracts.
- Adding `curate.yml` fields without a compiled policy consumed by code.
- Adding plugin UI for traces before backend trace payloads exist.

## 7. Minimum Evidence That The Future Implementation Is Real

When v0.3.1 is implemented, the following should be directly inspectable:

- `wiki prompt list` shows prompt ids and versions.
- `wiki prompt trace TRACE_ID` shows prompt input/output hashes and validators.
- `wiki curate plan --workspace PATH --json` shows compiled `CurationPolicy`.
- `wiki query --mode global ...` returns community report ids.
- `wiki query --mode explore ...` returns follow-up questions and memory paths.
- `.curator/state.sqlite` contains `source_spans`, `knowledge_units`,
  `graph_entities`, `graph_relations`, `community_reports`, `prompt_runs`,
  `curation_plans`, and `insight_candidates`.
- Plugin trace panel shows route, prompt id/version, source spans, reports, and
  insight candidates.
- MCP `curator_get_prompt_trace(trace_id)` returns the same trace as CLI.
- Backprop from an Exhibition creates an insight candidate or generated-artifact
  patch plan without modifying original source truth.

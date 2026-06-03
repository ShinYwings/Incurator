# External RAG Systems Review For v0.3.1

## 1. Purpose

This document reviews modern RAG, GraphRAG, memory, tree retrieval, property
graph, and codebase indexing systems. The goal is not to copy any one system.
The goal is to identify which mechanisms should be absorbed into Incurator's
curation-native compiler.

## 2. Microsoft GraphRAG

References:

- <https://microsoft.github.io/graphrag/index/overview/>
- <https://microsoft.github.io/graphrag/query/overview/>
- <https://microsoft.github.io/graphrag/query/local_search/>
- <https://microsoft.github.io/graphrag/query/global_search/>
- <https://microsoft.github.io/graphrag/query/drift_search/>

### 2.1 Indexing Pipeline

GraphRAG indexes unstructured text by extracting structured data:

- entities;
- relationships;
- claims;
- community structure;
- community summaries and reports;
- embeddings.

The important architectural decision is that global understanding is not left to
query-time top-k vector search. GraphRAG builds dataset-level semantic structure
in advance.

### 2.2 Retrieval Pipeline

GraphRAG defines multiple query modes:

- Local Search: entity-centered retrieval over graph data plus raw text chunks.
- Global Search: community-report search and map-reduce synthesis for
  whole-dataset questions.
- DRIFT Search: hybrid global/local exploration. It starts with community
  context, generates follow-up questions, and uses local search refinements.
- Question Generation: candidate follow-up questions for deeper investigation.

### 2.3 Prompt And Orchestration Strategy

GraphRAG's prompt strategy is mode-specific. Local search builds context from
entity relationships and source chunks. Global search uses a map step to produce
rated intermediate responses from community reports, then a reduce step to
aggregate important points. DRIFT uses a query state and expansion hierarchy.

**Update strategy.** GraphRAG's architecture makes index freshness a first-class
engineering concern because community reports and graph neighborhoods can become
stale independently of raw chunks. For Incurator, this implies that every
generated graph/report artifact needs source hashes, prompt versions, and
dependency edges so changed notes can invalidate only affected artifacts instead
of requiring a full-vault rebuild.

### 2.4 Strengths

- Strong whole-dataset reasoning.
- Clear query-mode separation.
- Community reports make broad questions answerable.
- DRIFT provides a useful model for exploratory research and "what am I missing"
  questions.
- Local search uses structured graph entry points rather than only chunk
  similarity.

### 2.5 Weaknesses

- Indexing can be expensive.
- LLM-generated graph structure can introduce noise.
- It is not designed around Obsidian note authorship, source-truth protection,
  promotion, or backprop.
- Community reports can become stale if incremental update is not carefully
  managed.
- It treats community reports as query aids; Incurator must also handle
  workspace-specific Exhibition staging.

### 2.6 Adopt For Incurator

- Entity/relation/claim extraction as part of L2/L3.
- Community reports as L3-adjacent or L3.5 curation artifacts.
- Local/global/explore query routing.
- DRIFT-like exploration for insight discovery.
- Map-reduce global synthesis for broad `curate.yml` questions.

### 2.7 Reject Or Modify

- Do not replace Exhibition with generic community report answers.
- Do not treat LLM-generated reports as human truth.
- Do not hide source provenance behind community summaries.
- Do not build a separate GraphRAG product outside the Curator pipeline.

## 3. LightRAG

References:

- <https://arxiv.org/abs/2410.05779>
- <https://github.com/HKUDS/LightRAG>

### 3.1 Indexing Pipeline

LightRAG is designed around graph structures plus vector representations. Its
core motivation is that flat data representations produce fragmented answers
and miss dependencies. It uses dual-level retrieval to support both low-level
and high-level knowledge discovery.

### 3.2 Retrieval Pipeline

The key idea is combining graph retrieval and vector retrieval so related
entities and relationships are retrieved efficiently. It emphasizes speed and
incremental update.

**Prompt/orchestration strategy.** LightRAG is useful less because of a single
large synthesis prompt and more because it decomposes retrieval into low-level
and high-level graph/vector context. Incurator should adopt that orchestration
shape: route source-level questions to claim/source spans, route broad
workspace questions to concepts/reports, and then select a prompt contract that
matches the chosen evidence level.

**Update strategy.** LightRAG's emphasis on incremental updates maps directly to
vault behavior. Notes, PDFs, and workspace specs change frequently, so v0.3.1
should update graph/vector state by changed source id, source span hash, and
affected entity/relation set rather than rebuilding all curation artifacts after
every edit.

### 3.3 Strengths

- Lightweight graph/vector hybrid framing.
- Better fit for practical systems than fully heavyweight GraphRAG in some
  contexts.
- Incremental update is central.
- Good conceptual fit for a vault that changes as users write notes.

### 3.4 Weaknesses

- Less explicit about human-in-the-loop truth lifecycle.
- Less explicit about workspace-specific curation specs.
- Does not provide Incurator's promotion/backprop model.

### 3.5 Adopt For Incurator

- Graph+vector dual-level retrieval.
- Incremental graph update discipline.
- Retrieval that can move between low-level claims and high-level concepts.

### 3.6 Reject Or Modify

- Do not reduce Incurator to a simple graph/vector retriever.
- Add `curate.yml`, Exhibition, prompt trace, and backprop semantics around the
  graph/vector retrieval core.

## 4. HippoRAG And HippoRAG 2

References:

- <https://arxiv.org/abs/2405.14831>
- <https://arxiv.org/abs/2502.14802>
- <https://github.com/OSU-NLP-Group/HippoRAG>

### 4.1 Indexing Pipeline

HippoRAG uses knowledge graphs and Personalized PageRank to mimic associative
long-term memory. It is motivated by the limits of vector retrieval for
integrating new knowledge and retrieving multi-hop associations.

HippoRAG 2 extends the idea with deeper passage integration and more effective
online LLM use, targeting factual, sense-making, and associative memory.

### 4.2 Retrieval Pipeline

The core retrieval path uses graph associations and PPR-like traversal so a
query can activate related memory paths without iterative multi-call retrieval.

**Prompt/orchestration strategy.** HippoRAG's orchestration value is in turning a
query into activated associative paths before synthesis. For Incurator, that
means the prompt should not receive only "top chunks"; it should receive named
memory paths with entity hops, source spans, confidence, and the reason each hop
was traversed. The synthesis prompt can then explain why a prior note is
relevant to the current note-writing task.

**Update strategy.** Associative memory is fragile when graph edges are stale.
v0.3.1 should recompute or down-rank memory paths affected by changed entities,
changed relation extraction prompts, or newly promoted insight records. The
system should also preserve old path traces long enough to explain why a past
answer was produced.

### 4.3 Strengths

- Strong model for associative memory.
- Good for multi-hop questions.
- Efficient compared with iterative retrieval in some settings.
- Useful for "find related prior knowledge" behavior.

### 4.4 Weaknesses

- Graph quality is decisive; bad extraction creates bad memory paths.
- Provenance and source-span fidelity require extra design.
- Not naturally oriented around note-writing, Exhibition staging, or promotion.

### 4.5 Adopt For Incurator

- Memory paths as ranked graph walks.
- PPR-like traversal over entities, claims, concepts, sources, and Exhibitions.
- Associative retrieval for prior-knowledge discovery.

### 4.6 Reject Or Modify

- Do not let graph traversal outrank source truth.
- Every memory path must include source spans and confidence.
- `curate.yml` should constrain traversal depth, domains, and exclusion policy.

## 5. RAPTOR

Reference:

- <https://arxiv.org/abs/2401.18059>

### 5.1 Indexing Pipeline

RAPTOR recursively embeds, clusters, and summarizes chunks of text to create a
tree of summaries. The tree stores information at multiple abstraction levels.

### 5.2 Retrieval Pipeline

At query time, retrieval can use the tree to access both detailed chunks and
higher-level summaries. This helps with long documents and multi-step QA where
top-k small chunks miss the overall structure.

**Prompt/orchestration strategy.** RAPTOR's orchestration pattern is recursive:
summaries at one level become inputs to higher-level summaries and query
synthesis can choose the needed abstraction level. Incurator should adopt this
only as a controlled summarization prompt family with validators for source-span
coverage and summary drift, not as an uninspected automatic replacement for
Atoms or Concepts.

**Update strategy.** A tree summary must be invalidated upward when a leaf
source span changes. Incurator can adapt this with dependency edges: if a
section-level summary changes, invalidate the document summary, affected
community report inputs, and any Exhibition that pinned the old summary.

### 5.3 Strengths

- Solves a real problem: flat small chunks miss whole-document context.
- Useful for books, papers, long notes, and source collections.
- Works as an abstraction hierarchy.

### 5.4 Weaknesses

- Summaries can drift.
- Trees are less natural for cross-document entity relations.
- Pure tree hierarchy is weaker than a graph for associative memory.
- It does not model human promotion or backprop.

### 5.5 Adopt For Incurator

- Recursive summaries for long documents and large communities.
- Multi-level abstraction inside L1/L3/community reports.
- Retrieval over several abstraction levels.

### 5.6 Reject Or Modify

- Do not make RAPTOR tree the primary architecture.
- Pair recursive summaries with graph edges, source spans, and curation specs.

## 6. LlamaIndex Property Graph Index

Reference:

- <https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/>

### 6.1 Indexing Pipeline

LlamaIndex Property Graph Index constructs property graphs by applying
extractors to chunks. Entities and relations become graph nodes/edges with
metadata. The system supports several retrievers, including synonym, vector,
Text-to-Cypher, template, and custom retrievers.

### 6.2 Retrieval Pipeline

Retrieval is composed from sub-retrievers. The system can combine keyword,
synonym, vector, and graph traversal behavior.

**Prompt/orchestration strategy.** LlamaIndex's strongest prompt lesson is
contractual modularity: extractors and retrievers can be composed as explicit
components. Incurator should use that idea without surrendering ownership:
source extraction, entity extraction, community reporting, query routing, and
note-writing assistance should each have a named prompt contract and validator.

**Update strategy.** Property-graph systems make extractor versioning important.
If an entity/relation extractor changes, existing graph edges may need selective
revalidation even when source text did not change. v0.3.1 should store extractor
prompt id/version on generated graph records so schema and prompt migrations can
be planned rather than guessed.

### 6.3 Strengths

- Modular graph construction.
- Flexible retriever composition.
- Useful conceptual model for prompt and retriever contracts.
- Demonstrates that graph retrieval should be extensible rather than a single
  monolithic algorithm.

### 6.4 Weaknesses

- Framework abstraction can be heavier than needed.
- Direct adoption could obscure Incurator's own source-truth and promotion
  semantics.
- Production behavior depends heavily on extractor quality and graph store
  choices.

### 6.5 Adopt For Incurator

- Typed extractor modules.
- Retriever composition model.
- Custom curation retriever abstraction.

### 6.6 Reject Or Modify

- Do not wrap the whole system in LlamaIndex if it weakens project-specific
  contracts.
- Keep Incurator-owned schemas and prompt contracts.

## 7. Cursor Codebase Indexing

Reference:

- <https://cursor.com/blog/secure-codebase-indexing>

### 7.1 Indexing Pipeline

Cursor describes a codebase index built with:

- a Merkle tree over files and directories;
- SHA-256 hashes;
- syntactic chunks;
- embeddings;
- asynchronous background indexing;
- chunk-content embedding cache;
- index reuse via similarity hash and proof of access.

### 7.2 Retrieval Pipeline

Semantic search powers agent performance. The key product property is that the
agent can query quickly after opening a project, and the index updates cheaply
when only a few chunks change.

**Prompt/orchestration strategy.** Cursor's product lesson is that retrieval is
agent infrastructure. The prompt does not ask the user to manage the index; the
agent receives relevant codebase context as part of its normal work loop. For
Incurator, note-writing agents should similarly receive curated source spans,
Exhibition context, and prompt traces through backend tools without manually
walking the vault.

**Update strategy.** Cursor's Merkle/hash model is the clearest incremental
update lesson for Incurator. Markdown files, external PDF identities, extracted
source spans, prompt outputs, embeddings, and community reports should each have
stable hashes and invalidation dependencies so a small note edit updates only
the affected curation graph.

### 7.3 Strengths

- Excellent incremental indexing discipline.
- Strong time-to-first-query framing.
- Syntactic chunking respects code structure.
- Chunk cache avoids repeated embedding cost.
- Search is available as agent infrastructure, not as a user-only feature.

### 7.4 Weaknesses

- Codebase indexing is not knowledge curation.
- It does not include source truth/promotion/backprop semantics.
- It is optimized for code editing, not cross-source insight discovery.

### 7.5 Adopt For Incurator

- Merkle/hash-style source and chunk invalidation.
- Structure-aware chunking for Markdown/PDF/math.
- Async index/build with status visibility.
- Chunk-level embedding cache.
- Agent-ready context discovery.

### 7.6 Reject Or Modify

- Do not treat semantic search alone as understanding.
- Incurator chunks must carry source spans, curation role, and promotion status.

## 8. Combined Lessons

Incurator should absorb the following:

- GraphRAG's local/global/DRIFT mode separation.
- GraphRAG's community reports.
- LightRAG's graph/vector incremental practicality.
- HippoRAG's associative graph walks.
- RAPTOR's multi-level summaries.
- LlamaIndex's extractor/retriever modularity.
- Cursor's hash-based incremental indexing and agent-facing availability.

Incurator should reject:

- generic RAG without `curate.yml`;
- opaque vector-only memory;
- summaries without provenance;
- graph facts without source spans;
- query answers that bypass Exhibition/promotion lifecycle;
- prompt behavior without versioned contracts and evaluation.

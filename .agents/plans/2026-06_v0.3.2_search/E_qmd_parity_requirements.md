# v0.3.2 Search Internalization — E. qmd Parity Requirements

Date: 2026-06-04
Status: Read-only integrated analysis. This is a plan/spec-draft artifact, not an active spec.

## 0. Verdict

The user pushback is correct. qmd is not a simple embedding wrapper. The
Python backend must not replace it with only "Ollama embeddings + cosine".
That would regress exact matching, query expansion, context steering, chunk
quality, and reranking.

The replacement target is:

```text
authoritative DB rows
  -> robust FTS5 lexical retrieval
  -> chunked embedding retrieval
  -> typed query expansion (lex / vec / hyde + intent)
  -> RRF fusion with trace
  -> best-chunk reranking with a search reranker
  -> route-specific evidence expansion over the DAG
```

Search should become DB-native, but the retrieval quality bar is qmd parity or
better, not merely ownership of the index.

## 1. qmd Features That Matter

Source review covered qmd `README.md`, `docs/SYNTAX.md`, `src/store.ts`,
`src/llm.ts`, `package.json`, and the qmd fine-tune assets.

qmd quality comes from these concrete mechanisms:

- Hybrid retrieval: BM25/FTS5, vector retrieval, typed expansion, RRF, and
  reranking are all part of the normal pipeline.
- Typed query expansion: qmd expands plain queries into `lex`, `vec`, and `hyde`
  variants. `lex` routes to BM25, `vec` and `hyde` route to vector retrieval.
- Search-fine-tuned expansion: qmd defaults to a specialized query-expansion
  GGUF model (`qmd-query-expansion`) rather than a generic chat prompt.
- Dedicated models: qmd separates embedding, query expansion, and reranking
  models. The defaults are local GGUF models driven through `node-llama-cpp`.
- Cross-encoder-style reranking: qmd reranks candidate chunks, not full
  documents, using a ranking context. It deduplicates identical chunks, truncates
  to context, caches scores, and returns a model-specific score.
- Chunk-level retrieval: qmd embeds chunks with stable positions. Whole-document
  embeddings are not the parity target.
- Context/intent steering: qmd supports global, collection, and path-inherited
  context plus intent strings. For Incurator, the equivalent is DAG layer/KRS/
  workspace context.
- RRF discipline: qmd fuses multiple lists with RRF, gives original-query lists
  stronger weight, applies top-rank protection, and blends rerank score with
  retrieval position.
- Operational safeguards: embedding fingerprints, stale-vector detection,
  FTS-only degradation, model cache, CPU/GPU controls, context-size controls,
  line-aware snippets, and doc/path fidelity.

## 2. Required Python Parity Contract

### 2.1 Query Expansion

v0.3.2 must define a native query-expansion workflow:

- Deterministic expansion always runs first:
  - original query
  - English working query when language bridge produces one
  - quoted phrase and exact-token variants
  - acronym/alias variants from graph entities and source titles
  - KRS/workspace terms and route intent
  - simple morphology/prefix variants for technical terms
- LLM/search-model expansion runs when configured:
  - output must be typed as `lex`, `vec`, or `hyde`
  - malformed expansion must be rejected and traced
  - failure must degrade to deterministic expansion, not query failure
- The trace records:
  - expansion provider/model
  - every generated expansion
  - the backend each expansion routes to
  - rejected malformed expansions
  - fallback reason when model expansion is unavailable

### 2.2 Lexical Retrieval

FTS5 must support qmd-grade lexical cases:

- exact phrases
- negation
- prefix matching
- hyphenated identifiers like `nomic-embed-text`
- dotted identifiers and versions like `state.sqlite` or `v0.3.2`
- Korean/CJK search via trigram fallback or equivalent
- field/layer boosting

The parser and query builder must be tested directly. The target is not a raw
`MATCH ?` pass-through.

### 2.3 Chunked Vector Retrieval

Embeddings must be chunk-level:

- `search_documents` represent retrievable DB records.
- `search_chunks` represent stable chunks within those records.
- `search_embeddings` key vectors by chunk, provider, model, dimension, and
  dependency/input hash.
- Chunk text must preserve source provenance and position.
- Code fences, math blocks, and citations should not be split destructively.
- Vector search returns best chunks and then maps them back to records/evidence.

Whole-record embeddings may exist as an optimization or fallback, but they are
not sufficient for parity.

### 2.4 Context Tree Injection

Python should exceed qmd by making Incurator's DB graph explicit:

- Search seeds can be source spans, knowledge units, graph entities, relations,
  community reports, synthesis nodes, or memory paths.
- Evidence expansion should be route-specific:
  - `source_span` -> nearby spans in source/page/section order
  - `knowledge_unit` -> cited spans and linked entities
  - `entity` -> relation neighborhood, units, and source spans
  - `community_report` -> member entities/relations/spans
  - `synthesis_node` -> supporting reports/spans
  - `explore` -> memory paths seeded by hybrid hits
- Expansion/rerank prompts receive route, workspace KRS, layer, and graph context.

This is the place where a DB-native system can exceed qmd: qmd has path contexts;
Incurator has typed graph provenance.

### 2.5 RRF and Reranking

RRF must be deterministic and traceable:

- default `k = 60`
- original-query FTS/vector lists receive higher weight than expansion-derived lists
- trigram/CJK lexical list is down-weighted relative to primary BM25
- top-rank bonus or equivalent protection is documented
- candidate limit before rerank is documented, with qmd's `40` as the baseline
- trace records every contribution by list, rank, weight, backend score, and RRF contribution

Reranking is mandatory when configured for answer-producing routes:

- Rerank best chunks, not full bodies.
- Prefer a cross-encoder/search reranker or local GGUF-backed reranker.
- A generic chat LLM relevance prompt is degraded mode only.
- Rerank score is blended with retrieval position so a noisy reranker cannot
  obliterate strong exact matches.
- If reranker is unavailable, answer can proceed in RRF order only with explicit
  trace warnings.

## 3. Provider Decisions To Pin Before Code

Recommended default matrix:

| Capability | Preferred target | Degraded target |
|---|---|---|
| Embedding | local multilingual embedding model, likely `bge-m3` or `nomic-embed-text` via Ollama | FTS-only |
| Query expansion | local search-expansion GGUF or prompt contract benchmarked against qmd | deterministic expansion |
| Reranking | local cross-encoder/search reranker or GGUF reranker | RRF-only with warning |
| Vector engine | NumPy brute-force cosine | FTS-only |
| Accelerator | none in v0.3.2; `sqlite-vec` future threshold | none |

Open decision: whether to use `llama-cpp-python`/GGUF to mirror qmd's local model
story, or use Python transformer/cross-encoder packages. This should go through
`/grill-me` if latency, install size, and local-first purity need explicit tradeoff.

## 4. Acceptance Tests

Minimum tests before qmd can be retired:

- Typed expansion parses `lex`, `vec`, `hyde`, and `intent`.
- Invalid expansion is rejected with trace warning.
- FTS parser handles exact phrases, negation, prefix, hyphenated identifiers,
  dotted versions, and Korean/CJK queries.
- Chunker preserves code fences/math blocks and stable positions.
- Embedding lifecycle skips unchanged hashes, detects model/dim mismatch, and
  removes stale/incomplete vectors.
- Vector retrieval returns chunk provenance, not only record ids.
- RRF uses `k=60`, original-query weighting, candidate limit, top-rank protection,
  deterministic ordering, and explain traces.
- Rerank uses best chunks, caches scores, blends position-aware, and degrades
  with warnings when unavailable.
- Ambiguous intent query changes rank order under different intents.
- Hybrid retrieval matches or exceeds BM25-only and vector-only baselines on a
  seeded corpus.
- qmd parity smoke compares Python top-k against qmd on exact, semantic,
  ambiguous, Korean, and provenance-heavy queries before qmd is removed from docs.

## 5. Sources

- qmd repository: https://github.com/tobi/qmd
- qmd store implementation: https://github.com/tobi/qmd/blob/main/src/store.ts
- qmd LLM implementation: https://github.com/tobi/qmd/blob/main/src/llm.ts
- qmd syntax docs: https://github.com/tobi/qmd/blob/main/docs/SYNTAX.md
- qmd query-expansion fine-tune notes: https://github.com/tobi/qmd/tree/main/finetune

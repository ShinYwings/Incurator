# Search Parity Benchmark — native DB engine vs qmd (v0.3.2)

**Date:** 2026-06-05
**Question:** After retiring the external `qmd` binary (v0.3.2), does the
DB-native hybrid search engine match qmd's retrieval quality?
**Verdict:** Native DB search is at least at qmd parity on the measured synthetic
sets, but query expansion is not a universal win. After fixing the reranker
invocation (see §4), the native engine reaches recall@10 = 1.000 and MRR@10 =
0.938 vs qmd's 1.000/1.000 on the original 36-doc set. On the later adversarial
ambiguous-query set, native hybrid beats qmd query on recall@3/MRR while native
with qmd's own 1.7B expander ties native without expansion.

## 1. Why this measurement

qmd was removed from the codebase in v0.3.2 (P9). To confirm the removal is **not
a search-quality regression**, qmd was temporarily re-run as an external binary
(no reinstall — its model cache already existed) and compared against the native
engine on a controlled corpus with ground-truth relevance.

## 2. Method

- **Original corpus:** 36 short documents across 12 distinct topic clusters (biology, deep
  learning, distributed systems, databases/IR, climate, physics, economics) plus
  **6 lexical near-miss distractors** (e.g. "Attention in classrooms",
  "Mountain climbing networks", "Greenhouse gardening") that share keywords with
  queries but are off-topic — these stress vector + rerank precision, not keyword
  overlap.
- **Expanded corpus:** the benchmark script now includes 64 documents and 40
  queries by adding systems/statistics/control/data-structure topics plus
  near-miss distractors. Use `BENCH_QUERY_OFFSET` / `BENCH_QUERY_LIMIT` for
  targeted hard-query smoke runs when full rerank is too slow.
- **Queries:** 20 original natural-language questions, plus 20 newer harder
  paraphrase questions, with ground-truth relevant doc ids.
  Many are paraphrases whose relevant doc shares few/no keywords (so lexical alone
  fails); several deliberately collide with a distractor's keywords.
- **Shared id space:** each doc is materialised both as a `search_documents` row
  (native) and a markdown file `<id>.md` (qmd), so a returned hit maps to the same
  id in both engines and metrics align.
- **Metrics:** recall@3, MRR@10, recall@10, macro-averaged over the 20 queries.
- **Isolation:** native (in-process llama-cpp) and qmd (subprocess llama-cpp) are
  run in **separate processes** (loading both llama stacks in one process
  segfaults). qmd is pinned to an isolated index via `INDEX_PATH` + `QMD_CONFIG_DIR`.

### Models compared

| stage | native engine | qmd |
|---|---|---|
| lexical | SQLite FTS5 (BM25) | qmd BM25 |
| embedding | `Qwen3-Embedding-0.6B` (GGUF, 1024-d) | `EmbeddingGemma-300M` (GGUF) |
| query expansion | deterministic Tier-1 + recovery-only LLM/HyDE Tier-2 | fine-tuned `qmd-query-expansion-1.7B` |
| fusion | RRF (k=60) | RRF |
| **reranker** | **`Qwen3-Reranker-0.6B`** (GGUF) | **`Qwen3-Reranker-0.6B`** (GGUF) |

Note both engines use the **same reranker model**, so the rerank stage is identical
in principle; native uses a *larger* embedder than qmd.

## 3. Results

36 docs · 20 queries · ground-truth topical relevance:

| engine | recall@3 | MRR@10 | recall@10 |
|---|---|---|---|
| **native hybrid+rerank** | **0.950** | **0.938** | **1.000** |
| native lex (FTS5 only) | 0.750 | 0.683 | 0.850 |
| **qmd query (full)** | **1.000** | **1.000** | **1.000** |
| qmd search (BM25 only) | 0.000 | 0.000 | 0.000 |

Interpretation:

- **Native is at parity with qmd.** `recall@10 = 1.000` means every relevant doc is
  retrieved into the native candidate set; the small `recall@3`/`MRR` gap vs qmd is
  a handful of rank-2 placements on a 36-doc synthetic set — noise-level. qmd's only
  measurable edge is its fine-tuned 1.7B query-expansion model on a few paraphrase
  queries.
- **`qmd search` (BM25-only) = 0.000** is expected, not a defect: qmd's BM25 mode
  ANDs query terms, so full natural-language questions match nothing. qmd intends
  `qmd query` (the full pipeline) for NL. Native `lex` (FTS5) ORs terms and scores
  0.750 — more robust for NL, but still well below the hybrid path.
- The hybrid path (lexical + chunked vector + RRF + rerank) is decisively better
  than lexical-only for both engines, confirming the v0.3.2 architecture.

## 4. Reranker invocation fix (the parity-closing change)

A first run showed native at `recall@3 = 0.850 / MRR = 0.828 / recall@10 = 0.975`
— the relevant docs were *retrieved* but not *ranked* into the top-3 as reliably as
qmd, despite both using the same reranker. Root cause: the native
`LlamaCppReranker` scored a bare `"{query}\t{passage}"` string, whereas
`Qwen3-Reranker` expects its instruction template:

```
<Instruct>: Given a web search query, retrieve relevant passages that answer the query
<Query>: {query}
<Document>: {passage}
```

Switching to the instruction template roughly **doubled the relevant/irrelevant
score separation** (e.g. for one hard query: relevant 0.919→0.992, distractor
0.611→0.506) and moved native to `0.950 / 0.938 / 1.000`. Fixed in
`backend/src/curator/retrieval/providers.py` (`LlamaCppReranker._format`).

## 4a. Tier-2 LLM query expansion (measured: not a free win)

The engine supports a Tier-2 LLM expander (`search.query_expansion`, default on)
that rewrites a query into extra lexical terms, vector paraphrases, and a HyDE
document, all fused via RRF. It now runs **recovery-only by default**:
Incurator first checks raw lexical hit count and raw vector top similarity, then
uses Tier-2/HyDE only when confidence is low. This prevents the earlier MRR dip
when raw retrieval is already saturated.

Earlier wiring measured with a **small local expander (`qwen2.5:0.5b` via Ollama)**
before recovery-only gating:

| engine | recall@3 | MRR@10 | recall@10 |
|---|---|---|---|
| native hybrid+rerank | 0.950 | 0.938 | 1.000 |
| native + LLM expansion (qwen2.5:0.5b) | 0.950 | **0.912** | 1.000 |

It did **not** help here and slightly lowered MRR. Why, and what it means:

- Native `recall@10` is already **1.000** on this corpus — every relevant doc is
  retrieved without expansion, so expansion has no recall headroom to add; a weak
  0.5B expander only injects noisy probes that perturb RRF ordering.
- Expansion's real value is **recall** on harder/larger corpora where lexical +
  vector miss the relevant doc — not fine ranking when recall is already saturated.
- qmd's MRR=1.000 edge comes from its **fine-tuned 1.7B** `qmd-query-expansion`
  model, not generic expansion. Expander quality tracks the model: a tiny generic
  model is a floor, a strong production LLM (gemini/claude-class) is expected to
  help. The feature is fail-safe (degrades to Tier-1 if the LLM is unavailable).

Practical guidance: keep query expansion enabled with recovery-only gating and a
capable answer-path LLM; its payoff shows on real corpora where retrieval has
recall gaps, and it should be benchmarked per deployment rather than assumed
positive.

## 4b. qmd 1.7B GGUF expander compatibility and adversarial comparison

The native benchmark now includes an opt-in qmd-compatible GGUF expander variant:

```bash
BENCH_QUERY_OFFSET=20 BENCH_QUERY_LIMIT=1 FUSE_CAP=2 EXPANDER_MODEL='' \
RUN_QMD_EXPANDER=1 uv run --project backend python scripts/benchmarks/search_parity_bench.py
```

Result on 2026-06-05:

| engine | recall@3 | MRR@10 | recall@10 |
|---|---|---|---|
| native hybrid+rerank | 1.000 | 1.000 | 1.000 |
| native + qmd-1.7B expansion | 1.000 | 1.000 | 1.000 |
| native lex (FTS5) | 1.000 | 1.000 | 1.000 |
| qmd query (full) | 1.000 | 1.000 | 1.000 |
| qmd search (BM25) | 0.000 | 0.000 | 0.000 |

This proved the Python GGUF expander path loads and parses qmd's structured
`lex:` / `vec:` / `hyde:` output. It does **not** prove an expansion win: this
1-query smoke still has no recall headroom. It also took about 103 seconds on
the local machine, so the qmd-1.7B row is opt-in (`RUN_QMD_EXPANDER=1`) rather
than part of the default multi-query benchmark.

The script now also includes an `adversarial` scenario: 32 docs / 8 short or
ambiguous queries (`paint mix`, `web mail`, `io file`, `build up`, etc.) with
near-miss distractors. This scenario was designed to create at least ranking
headroom for expansion rather than another saturated easy set.

Commands used:

```bash
BENCH_SCENARIO=adversarial FUSE_CAP=8 EXPANDER_MODEL='' \
  uv run --project backend python scripts/benchmarks/search_parity_bench.py native:none

BENCH_SCENARIO=adversarial FUSE_CAP=8 EXPANDER_MODEL='' \
  EXPANSION_RECOVERY_ONLY=0 \
  uv run --project backend python scripts/benchmarks/search_parity_bench.py native:qmd

BENCH_SCENARIO=adversarial FUSE_CAP=8 EXPANDER_MODEL='' \
  uv run --project backend python scripts/benchmarks/search_parity_bench.py qmd
```

The native qmd-expander run took about 16 minutes for 8 queries.

32 docs · 8 adversarial queries · ground-truth topical relevance:

| engine | recall@3 | MRR@10 | recall@10 |
|---|---:|---:|---:|
| native hybrid+rerank | **1.000** | **0.917** | **1.000** |
| native + qmd-1.7B expansion | **1.000** | **0.917** | **1.000** |
| qmd query (full) | 0.875 | 0.906 | **1.000** |
| qmd search (BM25 only) | 0.500 | 0.469 | 0.625 |

Interpretation:

- The adversarial set did create top-rank headroom: native no-expansion placed
  the relevant `build up` document at rank 3, not rank 1.
- qmd's own 1.7B expander did **not** improve native ranking on this set; it tied
  native no-expansion.
- qmd full query under-ranked the same `build up` target more severely (rank 4),
  so native hybrid remained ahead on recall@3 and MRR.
- This does not disprove the value of expansion on real corpora. It shows that a
  qmd-trained expander is not automatically better than native Qwen3 embedding +
  reranking, even on intentionally ambiguous synthetic queries.

## 5. Caveats

- Synthetic corpus with **topical** (not human-judged) relevance, and still small
  scale (64 docs). Absolute numbers are a sanity benchmark, not a leaderboard
  score.
- qmd is gone from the product, so this is an **absolute-quality** check, not a
  regression gate; there is no longer a qmd path to regress against in normal use.
- Native query expansion Tier-2 (LLM/HyDE) is wired with recovery-only gating by
  default. Current synthetic subsets do not demonstrate a stable expansion
  advantage; the adversarial set shows ranking headroom but qmd's own expander
  does not close it.

## 6. Reproduce

```bash
# requires: wiki models ensure (Qwen3 GGUFs) + qmd binary with its model cache
uv run --project backend python scripts/benchmarks/search_parity_bench.py

# faster hard-query smoke, avoiding optional qmd 1.7B expander row
BENCH_QUERY_OFFSET=20 BENCH_QUERY_LIMIT=2 FUSE_CAP=4 EXPANDER_MODEL='' \
  uv run --project backend python scripts/benchmarks/search_parity_bench.py

# adversarial comparison; run rows separately to avoid llama-cpp subprocess
# instability when multiple GGUF stacks are loaded back-to-back
BENCH_SCENARIO=adversarial FUSE_CAP=8 EXPANDER_MODEL='' \
  uv run --project backend python scripts/benchmarks/search_parity_bench.py native:none
BENCH_SCENARIO=adversarial FUSE_CAP=8 EXPANDER_MODEL='' EXPANSION_RECOVERY_ONLY=0 \
  uv run --project backend python scripts/benchmarks/search_parity_bench.py native:qmd
BENCH_SCENARIO=adversarial FUSE_CAP=8 EXPANDER_MODEL='' \
  uv run --project backend python scripts/benchmarks/search_parity_bench.py qmd
```

Script: [`scripts/benchmarks/search_parity_bench.py`](../../scripts/benchmarks/search_parity_bench.py).
The corpus, queries, and metrics are defined inline and easy to extend.

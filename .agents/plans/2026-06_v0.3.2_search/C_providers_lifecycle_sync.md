# v0.3.2 — Embedding / Rerank / Query-Expansion Providers, Embedding Lifecycle, and Local-First Sync

Companion design doc for `.agents/plans/2026-06_v0.3.2_search_internalization_plan.md`.
Scope: **design only**. No runtime code, specs, or other plan files are modified by this document.

## 2026-06-05 Provider Default Update

The original provider recommendations in this artifact are superseded by
`.agents/plans/2026-06_v0.3.2_model_provisioning_decision_plan.md`:

- default embedder: `llama-cpp::qwen3-embedding-0.6b`
  (`Qwen/Qwen3-Embedding-0.6B-GGUF` /
  `Qwen3-Embedding-0.6B-Q8_0.gguf`)
- default reranker: `llama-cpp::qwen3-reranker-0.6b`
  (`ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF` /
  `qwen3-reranker-0.6b-q8_0.gguf`)
- before loading those llama-cpp search GGUFs, Incurator issues a best-effort
  Ollama unload request (`keep_alive: 0`) for configured Incurator Ollama LLM
  models to protect the 2.5 GB VRAM budget.

The earlier warning against community Qwen3-Reranker GGUFs was valid: broken
conversions can omit `cls.output.weight` and return near-zero scores. It should
now be read narrowly as "do not trust arbitrary community Qwen3 reranker GGUFs."
The selected `ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF` artifact is the corrected
candidate referenced by llama.cpp maintainers in issue #16407 and must be
validated by an Incurator live smoke check before parity claims.

This doc answers five questions for the in-DB hybrid search work:
1. A provider abstraction for `embed()` / `rerank()` / `expand_query()` that fits the existing `llm.py` multi-provider pattern.
2. The embedding *lifecycle* (when vectors are produced, how they are keyed, when they are re-computed or invalidated).
3. The *storage* shape in `state.sqlite` + size estimates.
4. The **local-first SYNC** analysis — the critical part, because `state.sqlite` is local-per-device and not synced.
5. A failure / degradation matrix.

Everything below is grounded in the existing code:
- `backend/src/curator/llm.py` — the `ChatMessage` interface, `OllamaClient`, `FailoverClient`, `build_client()`, `make_client_by_key()`, `_make_*` factories, `detect_ram_gb()`.
- `backend/src/curator/config.py` — `DEFAULT_CONFIG`, `load_config()` (global + vault merge), `split_provider_model()`, `paths_from_config()`.
- `backend/src/curator/constants.py` — backend keys (`BACKEND_OLLAMA`, `BACKEND_DEEPSEEK_API`, …), default models, `STATE_DB`.
- `backend/src/curator/db.py` — `SCHEMA_VERSION`, `SCHEMA_SQL`, `artifact_dependencies` (with `dependency_hash`), `knowledge_units`, `synthesis_nodes`, `community_reports`, `source_spans`.

---

## 0. Constraints inherited from the codebase (read these first)

These are non-negotiable facts the design must respect:

1. **`state.sqlite` is the single source of truth AND it is local-per-device.** It is gitignored / stignored. Only vault *source* files (`02_Wiki`, `03_Notes`, `04_Resources`, `05_Assets`) sync via Syncthing + GitHub. Therefore **anything stored only in the DB is, by definition, rebuildable per device** — and embeddings stored in the DB are *not* synced.
2. **Offline-capable is a product invariant.** The system must remain usable with *no* network and *no* reachable embedding provider. This forces graceful degradation to FTS5-only.
3. **The existing provider pattern is a duck-typed client object**, not an ABC. Every client exposes `chat`, `chat_stream`, `ensure_ready`, `ping`, `close`, `get_and_reset_token_usage`, and (for local) `clone`/`unload`. There is no `embed` method anywhere today — embeddings were owned by the external `qmd` binary. This is genuinely new surface area.
4. **Provider selection is config-driven** via `llm.primary` / `llm.fallback` in `provider::model` form, parsed by `split_provider_model()`, built by `build_client()` into a `FailoverClient`. The embedding stack must mirror this exact idiom so users configure it the same way.
5. **`FailoverClient`** already gives us ordered-provider + background-probe + auto-promotion semantics for free. The embedding layer should reuse this rather than reinvent it.
6. **RAM-based defaulting already exists** (`detect_ram_gb()`, `RAM_THRESHOLD_GB = 16`, `OllamaClient.optimal_context_window`). Embedding-provider defaulting should follow the same "small box ⇒ cloud-leaning, big box ⇒ local" instinct, but with embedding-specific thresholds (embedding models are far smaller than chat models).

---

## 1. Provider abstraction

### 1.1 Shape: a parallel, duck-typed `Embedder` family — NOT bolted onto chat clients

The chat clients (`OllamaClient`, `DeepSeekApiClient`, the CLI clients) are designed around *one prompt → one text completion*. Embedding is a different contract: *batch of texts → batch of fixed-dim float vectors*, plus a **dimension** and a **model fingerprint** that the storage layer must persist. The reranker is *(query, list[doc]) → list[score]*. Query-expansion is *(query) → structured variants* and is genuinely just a chat call.

Recommendation:
- **`embed()` and `rerank()` get their own client family** (`OllamaEmbedder`, `CloudEmbedder`, `LocalGgufReranker`, …), selected by a `build_embedder(config)` / `build_reranker(config)` factory that mirrors `build_client()` / `make_client_by_key()` exactly (same `provider::model` parse, same `FailoverClient` wrapping, same RAM defaulting).
- **`expand_query()` reuses the existing chat client** (`build_client(config)`), because it is a chat completion with a fixed prompt contract. Do not create a third client family for it. A *dedicated query-expansion model* (if configured) is just a different `provider::model` value resolved through the existing factory — i.e. `search.query_expansion.model: "ollama::<gguf>"`.

This keeps the CLI-only clients (Claude Code, Antigravity `agy`, Codex) out of the embedding path entirely — they cannot emit vectors and must never be selected as an embedder. The factory will simply refuse to build an embedder for those backend keys (see §5).

### 1.2 The `Embedder` interface (duck-typed, mirrors `OllamaClient`)

```text
class Embedder (protocol, not enforced ABC — match llm.py's duck-typing style):
    model: str                       # e.g. "bge-m3"
    dim: int                         # 1024 for bge-m3; 768 for nomic-embed-text
    provider_key: str                # "ollama" | "deepseek-api" | "openai-api" | ...

    def fingerprint(self) -> str     # stable id stored next to every vector; see §1.6
    def embed(
        self,
        texts: list[str],
        *,
        kind: str = "document",      # "document" | "query"  (asymmetric models / prefixes)
        batch_size: int = 64,
        timeout: float | None = None,
    ) -> list[list[float]]           # len == len(texts); each inner len == self.dim
    def ensure_ready(self) -> None   # raises EmbedderError subclass if not operational
    def ping(self) -> bool
    def close(self) -> None
    def clone(self) -> "Embedder"    # for thread-parallel batches, like OllamaClient.clone()
```

`kind` matters: BGE-M3 is symmetric-ish but several strong models (e5 family, nomic-embed) want a `search_document:` / `search_query:` prefix or an instruction string for asymmetric retrieval. The embedder owns that detail so callers stay clean. `embed()` MUST return exactly `self.dim`-length vectors or raise — the storage layer relies on it.

### 1.3 The `Reranker` interface

```text
class Reranker (protocol):
    model: str
    provider_key: str
    def fingerprint(self) -> str
    def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_k: int | None = None,
        timeout: float | None = None,
    ) -> list[tuple[int, float]]     # (original_index, score), sorted desc
    def ensure_ready(self) -> None
    def ping(self) -> bool
    def close(self) -> None
```

Reranking is *optional* and *answer-time only* (per the parent plan §3.6); it never runs during ingest. If no reranker is configured/reachable, fusion (RRF) output is used directly.

### 1.4 `expand_query()` — reuse the chat client, no new family

```text
def expand_query(chat_client, query, *, intent, context) -> ExpandedQuery
    # ExpandedQuery = {lex: list[str], vec: list[str], hyde: str, intent: str}
```

- **Deterministic expansion runs first and unconditionally** (synonyms, identifier de-hyphenation, CJK trigram fallback) so search works with zero LLM.
- If `search.query_expansion.model` is configured AND the chat client pings, an LLM pass produces `lex`/`vec`/`hyde` variants. The model is resolved via the existing `make_client_by_key()` so it can be a small local GGUF, the main chat model, or a cloud model — *user's choice, same config idiom*.
- A generic chat prompt is the **degraded** path (parent plan §0 is explicit: "A generic chat prompt is allowed only as a degraded fallback, never as the parity target").

### 1.5 Config surface (extends `DEFAULT_CONFIG["search"]`)

Today `DEFAULT_CONFIG["search"] = {"backend": "qmd", "rerank": True}`. v0.3.2 replaces this. Proposed shape, using the **same `provider::model` string idiom** as `llm.primary`:

```yaml
search:
  backend: native            # was "qmd"
  embedding:
    primary:  "llama-cpp::qwen3-embedding-0.6b"  # provider::model, parsed by split_provider_model
    fallback: ""                        # e.g. "ollama::bge-m3"
    dim: 1024                           # MUST match model; stored in fingerprint, validated
    batch_size: 64
    timeout: 60
    enabled: true                       # false ⇒ FTS5-only, no vectors ever generated
    gguf_repo: "Qwen/Qwen3-Embedding-0.6B-GGUF"
    gguf_file: "Qwen3-Embedding-0.6B-Q8_0.gguf"
  rerank:
    enabled: true
    primary:  "llama-cpp::qwen3-reranker-0.6b"
    fallback: ""
    timeout: 30
    gguf_repo: "ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF"
    gguf_file: "qwen3-reranker-0.6b-q8_0.gguf"
  query_expansion:
    enabled: true
    model: ""                # "" ⇒ reuse llm.primary chat model; else provider::model
    deterministic_only: false
  fusion:
    rrf_k: 60
    candidate_limit: 200
  ollama:
    host: "http://127.0.0.1:11434"   # may differ from llm.ollama.host
```

Because `load_config()` deep-merges global config over `DEFAULT_CONFIG`, machine-specific overrides (e.g. a cloud API key, a different Ollama host) live in the **global** config file, while the synced vault config carries portable defaults. This matches the existing `external.roots` / Zotero pattern (machine-local paths go global, not in the synced vault).

### 1.6 Model "fingerprint" (the load-bearing identity string)

Every stored vector must carry enough identity to detect a model/dimension change. Define:

```text
fingerprint = f"{provider_key}:{model}:{dim}:{normalize}:{prefix_scheme}:v1"
# example: "ollama:bge-m3:1024:l2norm:bgem3:v1"
```

- `provider_key` + `model` + `dim` are obvious.
- `normalize` records whether vectors were L2-normalized at write time (so cosine == dot product). **Recommendation: always L2-normalize on write** so query-time similarity is a plain dot product (cheaper, and avoids re-normalizing the whole table if the search code changes its mind).
- `prefix_scheme` captures the asymmetric prefix/instruction convention (changing it changes the vectors even if model+dim are identical).
- trailing `:v1` is an internal embedding-pipeline version so we can force a global re-embed if our chunking/normalization logic changes without the model changing.

If a chunk's stored fingerprint != the active embedder's fingerprint, that chunk is **stale** and must be re-embedded (§2.4). This is how a model swap or a dimension change is detected without a schema migration.

### 1.7 Concrete recommended default models (with citations)

**Embedding — previous default candidate: `bge-m3` (1024-dim) via Ollama.**

Rationale and tradeoffs:
- Incurator is bilingual EN/KR by design (paired EN/KR guides, Korean users). The original `nomic-embed-text` is **English-specialized and does not place Korean and English sentences of the same meaning near each other**; BGE-M3 learns a shared cross-lingual space across 100+ languages and is the clear pick for Korean ([Medium: Korean/English embedding test](https://medium.com/@jongbaekim0710/test-of-multilingual-embedding-model-for-english-and-korean-8015b2957ca7), [ai-marketinglabs: NV-Embed vs BGE-M3 vs Nomic](https://ai-marketinglabs.com/lab-experiments/nv-embed-vs-bge-m3-vs-nomic-picking-the-right-embeddings-for-pinecone-rag)).
- BGE-M3: 568M params, ~1.2 GB on disk, **1024-dim**, 8192-token context. F16 inference ≈ **1.06 GB**; with default batching (batch 256 / len 512) VRAM climbs to ~5.7 GB. ~6 GB VRAM recommended for batched throughput, but it runs fine CPU/unified-memory for personal-KB volumes ([Ollama bge-m3 library](https://ollama.com/library/bge-m3), [Morph: Ollama embedding benchmarks/VRAM](https://www.morphllm.com/ollama-embedding-models)).
- BGE-M3 also emits **sparse vectors alongside dense** — a natural future hybrid signal — and is "the right pick for multilingual + long-document RAG," still competitive in 2025–2026 ([BentoML: best open-source embedding models 2026](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models)). On MTEB its dense retrieval is competitive with `text-embedding-3-large` on English and notably stronger multilingually ([pristren: BGE-M3](https://pristren.com/blog/bge-m3-embeddings-multilingual/)).

**Lighter local alternative (offered, not default): `nomic-embed-text` (768-dim).**
- For English-mostly vaults on a small box, nomic gives similar English quality "at a quarter of the disk and memory cost" ([BentoML 2026](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models)). 768-dim halves vector storage vs 1024-dim (§3.4). Recommend it as an opt-in `dim: 768` profile for users who declare an English-only vault and want minimal RAM.
- A bilingual-but-lighter middle option is `multilingual-e5-large-instruct` (560M, 1024-dim, instruction-tuned, strong multilingual) ([MMTEB arXiv](https://arxiv.org/html/2502.13595v4)). Keep as documented alternative; default stays BGE-M3 for the dense+sparse and Korean strength.

**Cloud fallback — default: `openai-api::text-embedding-3-small` (configurable dim).**
- $0.02 / 1M tokens, 1536-dim native but supports **Matryoshka truncation to 1024/512/256** without retraining — so we can request 1024-dim to *match BGE-M3's dim* and keep one storage column shape ([pecollective: embedding specs 2026](https://pecollective.com/tools/text-embedding-models-compared/), [agentset: voyage vs 3-small](https://agentset.ai/embeddings/compare/voyage-35-vs-openai-text-embedding-3-small)). It is "the safe default… good enough for 90% of applications."
- The project already ships a `deepseek-api` OpenAI-compatible client; an OpenAI-compatible embedding client is a near-clone. **Critical caveat:** cloud and local fingerprints differ (different model → different vector space). You **cannot mix** vectors from two models in one similarity search. So the cloud "fallback" for embedding is NOT a per-request failover like chat — it is a *whole-corpus mode*: if you switch the active embedder, the corpus must be re-embedded with that model before vector search is valid again (§2.4, §4). Until re-embed completes, vector search degrades to FTS5-only (§5). This is the single biggest difference from the chat `FailoverClient` semantics and must be called out in the spec.

**Reranker — previous default candidate: `bge-reranker-v2-m3` (local cross-encoder).**
- Available as working GGUF (Q8_0 / Q4_K_M) and runs via llama.cpp with `pooling=rank` and via Ollama; BGE rerankers "work with rank pooling" out of the box ([HF: bge-reranker-v2-m3 GGUF](https://huggingface.co/klnstpr/bge-reranker-v2-m3-Q8_0-GGUF), [gist: llama-server rerank guide](https://gist.github.com/VooDisss/42bce4eb5c76d3c325633886c5e348ee)).
- Pairs naturally with BGE-M3 (same family, multilingual, Korean-capable) — the embedder and reranker share a language model lineage.
- **Avoid community Qwen3-Reranker GGUFs as default**: they are frequently broken (missing `cls.output.weight`, producing near-zero garbage scores ~4.5e-23) unless converted with the corrected pipeline ([llama.cpp issue #16407](https://github.com/ggml-org/llama.cpp/issues/16407), [gist guide](https://gist.github.com/VooDisss/42bce4eb5c76d3c325633886c5e348ee)). Offer Qwen3-Reranker only as an advanced opt-in with a validation check.
- Degraded fallback only: a search-fine-tuned LLM rerank prompt through the chat client. Never the parity target.

**Query expander — default: reuse `llm.primary` chat model**, deterministic-first.
- No separate model needed by default; users with a fine-tuned local expansion GGUF set `search.query_expansion.model: "ollama::<gguf>"` and it resolves through the existing factory.

### 1.8 Batching, timeouts, dimension handling, offline behavior

- **Batching.** Ollama's `/api/embed` accepts an array of inputs and processes them in parallel up to GOMAXPROCS; batch (~size 64–256) is ~2× slower than raw sentence-transformers but is the right call over per-text requests ([Ollama embeddings docs](https://docs.ollama.com/capabilities/embeddings), [ollama issue #7400](https://github.com/ollama/ollama/issues/7400)). Default `batch_size: 64`; expose it. Models that fit in VRAM are 5–30× faster than those that spill ([Morph](https://www.morphllm.com/ollama-embedding-models)) — relevant for the cold-start estimate in §4.
- **Parallelism.** Reuse the `OllamaClient.clone()` idiom: clone the embedder per worker thread so each owns its own `httpx.Client` (the existing code does exactly this for chat).
- **VRAM hygiene.** Reuse `OllamaClient.unload()` semantics (`keep_alive=0`) after a large embed pass so the embedding model is evicted and the chat/rerank model can load — the existing close() already does this for chat.
- **Timeouts.** Per-batch timeout from config (`search.embedding.timeout`, default 60 s). On timeout, retry the batch once at half size, then mark those chunks `pending` (not failed) so a later pass can finish them (§2, §5 partial-embeddings).
- **Dimension handling.** `dim` is validated on first successful embed: if the provider returns a vector whose length != configured `dim`, raise `EmbeddingDimensionMismatch` and refuse to write (prevents silently poisoning the table). For Matryoshka cloud models, request the configured `dim` explicitly so it matches the local default.
- **Graceful offline.** `build_embedder()` never raises at construction; `ensure_ready()`/`ping()` decide reachability at use time, exactly like `OllamaClient`. If the embedder is unreachable when embeddings are needed, the lifecycle marks chunks `pending` and the query path runs FTS5-only (§5). No crash, no partial corruption.

---

## 2. Embedding lifecycle

### 2.1 What gets embedded

Per the parent plan, **chunk-level** embeddings (whole-node embeddings alone are explicitly insufficient — plan §3.3). The authoritative text rows that feed search are:
`knowledge_units.statement`, `synthesis_nodes.statement`/`title`/`full_content`, `community_reports.summary`/`full_content`, and `source_spans.text_preview`. These are chunked (semantic chunks with stable positions and source-span provenance) into the new `search_chunks` table (parent plan §3, table owned by the schema spec, not this doc). **Each chunk** is the embedding unit.

### 2.2 When embeddings are generated

Two triggers, both opt-in-safe:

1. **Incrementally during compile** (preferred default). When `wiki add` / `wiki build` materializes/updates atoms, concepts, synthesis, or community reports, the chunker emits/refreshes `search_chunks` for the touched records, and **only the chunks whose `dependency_hash` changed** are embedded in the same pass (skip-when-unchanged). This keeps embeddings warm without a separate command and amortizes cost across normal ingest.
   - This stage degrades cleanly: if the embedder is unreachable during compile, chunks are written with `embedding_status='pending'` and compile still succeeds. FTS5 (which needs no model) is always populated.
2. **Dedicated `wiki reindex --embed`** (catch-up / bulk). Rebuilds FTS5 and then embeds all `pending`/stale chunks in batches. Used after a fresh device, after `wiki reset`, after a model change, or when compile ran offline. `wiki reindex` without `--embed` rebuilds only the lexical/FTS5 index (no model needed) — so a fully offline user can always at least restore lexical search.

### 2.3 Keying: chunk id + content `dependency_hash` + fingerprint

Each embedding row is keyed by:
- `chunk_id` — stable per chunk (record id + chunk position), so re-chunking a changed record replaces its chunk set deterministically.
- `dependency_hash` — content hash of the exact chunk text (same discipline as `community_reports.dependency_hash` and `artifact_dependencies.dependency_hash`). **Skip-when-unchanged:** if a chunk's current text hash == the stored `dependency_hash` AND the stored `model_fingerprint` == the active embedder fingerprint, the existing vector is reused; nothing is recomputed.
- `model_fingerprint` — from §1.6.

Re-embed happens iff `dependency_hash` changed **or** `model_fingerprint` changed.

### 2.4 Model / dimension change → re-embed

- A model or dim change flips the active embedder's `fingerprint`. Every stored vector now has a non-matching fingerprint and is treated as stale.
- The DB tracks the **active** fingerprint in a one-row `search_index_meta` table (parent plan §3). On `wiki reindex --embed`/next compile, the code compares each chunk's fingerprint to the active one and re-embeds the mismatched chunks. A full model swap therefore re-embeds the whole corpus, but **incrementally and resumably** (chunks flip from stale→done in batches; an interrupted run resumes from the remaining stale chunks).
- **Dimension change is special:** vectors of the old dim are not just stale, they are *unreadable for similarity* against the new ones. The query path filters vector candidates to those whose fingerprint == active fingerprint, so during a dim migration, vector search transparently ranks over only the already-migrated subset (and FTS5 covers the rest) until migration completes. No crash, monotonic improvement as re-embed progresses (§5 dimension-drift row).

### 2.5 Deletions / invalidation propagation (tie into `artifact_dependencies`)

The existing `artifact_dependencies` table already records `(artifact_id, artifact_type, depends_on_id, depends_on_type, dependency_hash)` and is the staleness index "at source-span/knowledge-unit granularity." Embeddings hook into it:

- **Record deleted** (e.g. a `knowledge_unit` or `synthesis_node` removed during recompile): its `search_chunks` rows are deleted by FK cascade (chunks reference their parent record), and the corresponding `search_embeddings` rows cascade with them. No orphan vectors.
- **Source span changes** (the root of `artifact_dependencies`): a changed span bumps the `dependency_hash` of dependent knowledge_units / synthesis_nodes; their chunk text changes; chunk `dependency_hash` changes; those chunks are re-embedded on the next pass. Invalidation propagates through the *existing* hash chain — embeddings ride on top of it rather than inventing a parallel mechanism.
- **`wiki reset`** drops the DB (see §4) → all embeddings gone → regenerated from synced source truth.

This is exactly the "incremental-invalidation discipline … we already have `artifact_dependencies` + `dependency_hash` — formalize it" note from the parent plan §A.

---

## 3. Storage

### 3.1 Tables (shape recommendation; the schema *spec* owns the canonical DDL)

Two new tables plus the parent plan's `search_chunks`. The embedding-specific shapes:

```sql
-- One row per chunk per model fingerprint. Float32 BLOB, fixed dim.
CREATE TABLE IF NOT EXISTS search_embeddings (
    chunk_id          TEXT NOT NULL,        -- FK -> search_chunks(id) ON DELETE CASCADE
    model_fingerprint TEXT NOT NULL,        -- §1.6, e.g. "ollama:bge-m3:1024:l2norm:bgem3:v1"
    dim               INTEGER NOT NULL,     -- 1024 / 768 — redundant w/ fingerprint, kept for fast checks
    vector            BLOB NOT NULL,        -- dim * 4 bytes, little-endian float32, L2-normalized
    dependency_hash   TEXT NOT NULL,        -- content hash of the chunk text at embed time
    created_at        TEXT NOT NULL,
    PRIMARY KEY (chunk_id, model_fingerprint),
    FOREIGN KEY (chunk_id) REFERENCES search_chunks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_search_embeddings_fp ON search_embeddings(model_fingerprint);

-- Single active-index descriptor (active fingerprint, counts, last build).
CREATE TABLE IF NOT EXISTS search_index_meta (
    id                   INTEGER PRIMARY KEY CHECK (id = 1),
    active_fingerprint   TEXT NOT NULL DEFAULT '',
    embedding_provider   TEXT NOT NULL DEFAULT '',
    embedding_model      TEXT NOT NULL DEFAULT '',
    dim                  INTEGER NOT NULL DEFAULT 0,
    total_chunks         INTEGER NOT NULL DEFAULT 0,
    embedded_chunks      INTEGER NOT NULL DEFAULT 0,
    pending_chunks       INTEGER NOT NULL DEFAULT 0,
    last_embed_at        TEXT NOT NULL DEFAULT ''
);
```

Notes:
- **Keying by `(chunk_id, model_fingerprint)`** lets a corpus temporarily hold two fingerprints during a model migration (old + new) so vector search keeps working over the migrated subset; a cleanup pass deletes non-active fingerprints once migration is done. This is the resumability mechanism from §2.4.
- **`embedding_status`** (`pending`/`done`) lives on `search_chunks` (parent plan owns that table); `search_embeddings` simply absent ⇒ pending for that fingerprint. Keeping status on the chunk avoids a 3-state join.
- **Float32 BLOB**, little-endian, contiguous — read with `numpy.frombuffer(blob, dtype='<f4')`. Brute-force cosine/dot in NumPy is the parent plan's chosen NN method (<50 ms at personal scale); `sqlite-vec` is deferred until a vault crosses the documented threshold (parent plan §4). No float16 by default: float32 keeps the brute-force dot product simple and exact; float16 is a future ~2× storage optimization, gated behind a fingerprint bump.

### 3.2 Why store dim+fingerprint redundantly

`dim` is derivable from `fingerprint`, but a cheap integer column lets the loader sanity-check `len(blob) == dim*4` before `frombuffer`, catching truncated/corrupt rows without parsing the fingerprint string on every read.

### 3.3 What is NOT stored in the DB

Nothing extra. No sidecar by default (see §4 recommendation). The vectors live only in `state.sqlite`, consistent with the "DB is the disposable, rebuildable index" philosophy.

### 3.4 Storage size estimates

Per-vector raw size = `dim × 4 bytes` (float32). Assume ~1 chunk row per record and a modest per-row SQLite overhead (~40–80 B for keys/hash/fingerprint/index entries; call it ~60 B amortized).

| chunks | 384-dim (1536 B/vec + ~60 B) | 768-dim (3072 B + ~60 B) | 1024-dim / bge-m3 (4096 B + ~60 B) |
|-------:|------------------------------:|-------------------------:|-----------------------------------:|
| 1,000  | ~1.5 MB                        | ~3.0 MB                  | ~4.0 MB                            |
| 10,000 | ~15 MB                         | ~30 MB                   | ~40 MB                             |
| 100,000| ~150 MB                        | ~300 MB                  | ~400 MB                            |

Reading: a realistic personal vault (low thousands of chunks) at the **default 1024-dim BGE-M3** costs single-digit MB — trivial. Even a large 100k-chunk vault is ~400 MB at 1024-dim, ~150 MB at 384-dim. These numbers drive the sync recommendation in §4 (a synced sidecar at 100k/1024-dim = ~400 MB of binary churn — a real Syncthing cost).

384-dim row is included because the OpenAI Matryoshka and `nomic` 256–768 options let a storage-constrained user pick a smaller dim; it is not the default.

---

## 4. Local-first SYNC analysis (critical)

**The core tension:** `state.sqlite` is local-per-device and not synced, so embeddings are **recomputed on every fresh device and after every `wiki reset`**. We have to decide whether that recompute is acceptable or whether embeddings should be persisted to a *synced sidecar*.

### 4.1 Cost / time to (re)generate all embeddings on a fresh device or after `wiki reset`

`wiki reset` (cli.py:1999) and a fresh device both start from synced source files with **no DB**. The full rebuild is: parse sources → LLM compile L1–L4 → chunk → embed. The **LLM compile** dominates wall-clock by far (many minutes to hours depending on corpus and chat backend). **Embedding is a small tail** on top of that:

- Throughput: on a 4090, `nomic-embed-text` hits ~12,450 tok/s at batch 256; `mxbai-embed-large` ~8,920 tok/s ([Morph](https://www.morphllm.com/ollama-embedding-models)). BGE-M3 is heavier but in the same order. On Apple-silicon unified memory or CPU it is much slower but still seconds-to-low-minutes for personal volumes.
- Order-of-magnitude estimate for the **embedding step alone** (chunk ≈ 200 tokens):
  - 1k chunks ≈ 200k tokens ≈ **<1 min** local on a GPU box; a few minutes CPU.
  - 10k chunks ≈ 2M tokens ≈ **2–5 min** GPU; ~15–30 min CPU/unified-memory if it spills VRAM (5–30× penalty, [Morph](https://www.morphllm.com/ollama-embedding-models)).
  - 100k chunks ≈ 20M tokens ≈ **20–40 min** GPU; potentially hours on a small box.
- **Key insight:** because LLM compile already has to re-run on a fresh device/`wiki reset` (the L1–L4 DAG is also DB-only and rebuilt from source), embedding does **not** add a new "fresh device is unusable" problem — it adds a *modest tail* to an already-expensive rebuild. The expensive thing (LLM compile) is the thing we accept recomputing; embeddings are cheaper than that.

### 4.2 Should embeddings be persisted to a *synced sidecar*?

**Recommendation: NO synced sidecar by default. Keep embeddings DB-local and rebuildable. Offer an OPTIONAL, explicitly-enabled, export/import sidecar as an escape hatch — not auto-synced.**

Reasoning (tradeoffs laid out):

Arguments *for* a synced sidecar:
- Avoids re-embedding cost on a new device (the §4.1 tail).
- Embeddings are deterministic-ish given (model, text), so they are "real" derived data worth caching.

Arguments *against* (decisive here):
1. **Philosophical consistency** — the entire v0.3.1/v0.3.2 thesis is "`state.sqlite` is the single source of truth; everything else is a disposable projection." A synced sidecar re-creates a *second* load-bearing, must-stay-in-sync artifact — exactly the DB↔file drift liability the plan kills by retiring qmd (parent plan §B). It would silently make the projection load-bearing again.
2. **Binary churn on Syncthing.** Embeddings change whenever *any* chunk text changes (re-compile rewrites statements). A monolithic vector blob would re-sync large binaries constantly. At 100k chunks / 1024-dim that is ~400 MB re-transferred on churn (§3.4). Even per-chunk sidecar files mean thousands of tiny binary files flapping — Syncthing index thrash and conflict-file spam.
3. **Merge conflicts / device divergence.** Two devices compiling at different times produce different DAGs (LLM nondeterminism), hence different chunks, hence non-mergeable vectors. A synced binary cache across divergent DBs is worse than useless — it would pair vectors with chunk ids that don't exist on the other device. Reconciling that needs the DB anyway.
4. **Fingerprint coupling.** If device A uses BGE-M3 (1024-dim) and device B uses nomic (768-dim) — entirely allowed, since the embedder is config/RAM-driven per device — a shared sidecar is *unusable* on the other device (wrong dim/space). Per-device config makes a single shared cache fundamentally wrong.
5. **The cost it avoids is the small tail, not the big cost.** Since LLM compile already must re-run on a fresh device, the sidecar only saves the §4.1 embedding minutes, not the dominant compile hours. Low payoff for high architectural cost.

**The escape hatch (optional, off by default):** a `wiki reindex --export-embeddings <file>` / `--import-embeddings <file>` pair that writes/reads a *self-describing* archive (fingerprint header + chunk `dependency_hash` + vectors). On import, vectors are accepted **only** for chunks whose current `dependency_hash` AND active fingerprint match — mismatches are ignored and re-embedded normally. This lets a power user manually carry embeddings to a second identical-config device without making them part of the sync contract, and it is self-validating (no drift risk because it re-checks hashes). It is explicitly **not** placed in a synced directory and **not** auto-generated.

### 4.3 Offline behavior when no embedding provider is reachable → FTS5-only

This is the offline-capable invariant in action:
- **Compile offline:** chunks are written, FTS5 is populated (no model needed), embeddings marked `pending`. Compile succeeds.
- **Query offline:** the hybrid pipeline detects zero usable vectors (or embedder unreachable) and runs **FTS5/BM25 + deterministic query expansion only**, skipping the vector arm of RRF and skipping rerank. Results are returned with a trace flag like `vector_skipped: provider_unreachable` so the user/agent knows retrieval was lexical-only.
- **Recovery:** when the provider returns, the next `wiki reindex --embed` (or next compile) drains `pending` chunks; vector search silently re-engages. Monotonic, no manual reset needed.
- FTS5 being **bundled in Python's SQLite (zero dependency, no model)** is what makes "always at least lexical search, even fully offline" a guarantee rather than a hope (parent plan §B).

---

## 5. Failure / degradation matrix

| Condition | Detection | Lifecycle behavior (ingest/compile) | Query behavior | Recovery |
|---|---|---|---|---|
| **Embedding provider unreachable** (Ollama down / cloud network fail) | `embedder.ping()` false or `ensure_ready()` raises | Chunks written; FTS5 populated; embeddings left `pending`; compile still succeeds | Vector arm skipped → **FTS5-only + deterministic expansion**; trace flags `vector_skipped`; no rerank | Next `wiki reindex --embed` / compile drains `pending`; vector search re-engages automatically |
| **Reranker unreachable / unconfigured** | `reranker.ping()` false or `rerank.enabled=false` | n/a (rerank is answer-time only) | Use RRF-fused order directly; trace flags `rerank_skipped` | Re-engages when reranker reachable; no re-embed needed |
| **Query-expansion model unreachable** | chat client ping false | n/a | Fall back to **deterministic expansion only** (always available); trace flags `expansion_deterministic_only` | Re-engages when chat client reachable |
| **Model mismatch — embedder config changed** (model swap, same dim) | chunk `model_fingerprint` != active fingerprint in `search_index_meta` | Mismatched chunks treated as stale → re-embedded incrementally/resumably (§2.4) | Vector candidates filtered to `active_fingerprint`; ranks over already-migrated subset; FTS5 covers the rest | Completes as re-embed drains; monotonic quality improvement |
| **Dimension drift** (e.g. bge-m3 1024 → nomic 768) | fingerprint dim != active dim | Old-dim vectors unreadable for similarity; flagged stale; full re-embed at new dim (resumable) | Vector search runs over new-dim subset only (length-validated); never mixes dims; FTS5 covers remainder | `wiki reindex --embed` finishes migration; cleanup pass deletes stale-fingerprint rows |
| **Partial embeddings** (timeout / crash mid-batch / offline compile) | `pending_chunks > 0` in `search_index_meta` | Batch retried once at half size, then remaining left `pending`; never marked corrupt | Hybrid runs with whatever vectors exist + FTS5; partial vector coverage is fine (RRF tolerates it) | Re-run `wiki reindex --embed`; idempotent (skip-when-unchanged) |
| **Dimension validation failure** (provider returns wrong-length vector) | `len(vector) != configured dim` on first embed | Raise `EmbeddingDimensionMismatch`; refuse to write any vector; abort that embed pass (do not poison table) | Unaffected for already-good rows; new chunks stay `pending` | Fix config `dim` to match model; re-run reindex |
| **Corrupt / truncated BLOB row** | `len(blob) != dim*4` at load time | n/a | Skip that vector (treat as missing), log once; row scheduled for re-embed | Next reindex re-embeds the chunk |
| **Embedder requested for non-embedding backend** (claude-code / antigravity-cli / codex-cli) | factory sees a CLI-only `provider_key` | `build_embedder()` raises `EmbedderConfigError` at config time (clear message: "Backend X cannot produce embeddings; set search.embedding.primary to ollama/openai-api/deepseek-api") | n/a (caught before any query) | User fixes `search.embedding.primary` |
| **Fresh device / `wiki reset`** | empty DB | Full rebuild: compile (dominant cost) then embed tail (§4.1); FTS5 available as soon as chunks exist | FTS5-only until embeddings drain; then full hybrid | Automatic via normal compile + `reindex --embed`; optional `--import-embeddings` escape hatch (§4.2) |

**Cross-cutting rule:** every degradation path **prefers returning lexical (FTS5) results over erroring**, and every skipped stage is recorded in the query trace so the dashboard/agent can see *why* retrieval was degraded (ties into the parent plan's trace persistence + dashboard click-to-use).

---

## 6. Summary of decisive recommendations

1. **Separate `Embedder` / `Reranker` client families** + `build_embedder()` / `build_reranker()` factories that mirror `build_client()` / `make_client_by_key()` and reuse `FailoverClient`. **`expand_query()` reuses the chat client** — no third family.
2. **Default embedder: `llama-cpp::qwen3-embedding-0.6b` (1024-dim, L2-normalized).** `ollama::bge-m3` remains a compatibility/fallback profile. Treat any embedder switch as a *whole-corpus re-embed mode*, not a per-request failover.
3. **Default reranker: `llama-cpp::qwen3-reranker-0.6b`** using the corrected `ggml-org` Q8_0 GGUF with live smoke validation. Generic chat rerank = degraded only.
4. **Lifecycle:** embed incrementally during compile (skip-when-unchanged via chunk `dependency_hash`) + `wiki reindex --embed` for catch-up. Re-embed iff `dependency_hash` OR `model_fingerprint` changed. Invalidation/deletion rides the existing `artifact_dependencies` + FK-cascade chain.
5. **Storage:** `search_embeddings(chunk_id, model_fingerprint, dim, vector BLOB float32, dependency_hash)` keyed `(chunk_id, fingerprint)` for resumable migrations; `search_index_meta` holds the active fingerprint + counts. Sizes are trivial at personal scale (~4 MB / 1k chunks at 1024-dim; ~400 MB at 100k).
6. **Sync:** **NO synced sidecar by default** — embeddings stay DB-local and rebuildable; the §4.1 cost is a modest tail on the already-mandatory LLM compile. Offer an optional, self-validating `--export/--import-embeddings` escape hatch that is not auto-synced and re-checks hashes on import. Avoids drift, binary churn, divergent-device merge conflicts, and per-device fingerprint mismatch.
7. **Offline:** always degrade to **FTS5-only** (bundled, no model) when no embedder/reranker/expander is reachable; trace every skipped stage; recover automatically on next reindex/compile.

---

## Sources

- [Test of Multilingual Embedding Model for English and Korean (Medium)](https://medium.com/@jongbaekim0710/test-of-multilingual-embedding-model-for-english-and-korean-8015b2957ca7)
- [Ollama Embedding Models: Benchmarks, VRAM, and Which to Use (Morph)](https://www.morphllm.com/ollama-embedding-models)
- [NV-Embed vs BGE-M3 vs Nomic (ai-marketinglabs)](https://ai-marketinglabs.com/lab-experiments/nv-embed-vs-bge-m3-vs-nomic-picking-the-right-embeddings-for-pinecone-rag)
- [The Best Open-Source Embedding Models in 2026 (BentoML)](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models)
- [bge-m3 (Ollama library)](https://ollama.com/library/bge-m3)
- [BGE-M3: Dense, Sparse, Multi-vector (pristren)](https://pristren.com/blog/bge-m3-embeddings-multilingual/)
- [MMTEB: Massive Multilingual Text Embedding Benchmark (arXiv)](https://arxiv.org/html/2502.13595v4)
- [Embedding Model Specs 2026: Dimensions, Price, MTEB (pecollective)](https://pecollective.com/tools/text-embedding-models-compared/)
- [voyage-3.5 vs OpenAI text-embedding-3-small (agentset)](https://agentset.ai/embeddings/compare/voyage-35-vs-openai-text-embedding-3-small)
- [bge-reranker-v2-m3 Q8_0 GGUF (Hugging Face)](https://huggingface.co/klnstpr/bge-reranker-v2-m3-Q8_0-GGUF)
- [llama-server models.ini guide for Qwen3 reranker + embedding (GitHub gist)](https://gist.github.com/VooDisss/42bce4eb5c76d3c325633886c5e348ee)
- [llama.cpp rerank output wrong with Qwen3-Rerank (Issue #16407)](https://github.com/ggml-org/llama.cpp/issues/16407)
- [Ollama Embeddings capabilities (docs)](https://docs.ollama.com/capabilities/embeddings)
- [Ollama REST embeddings slower than sentence-transformers (Issue #7400)](https://github.com/ollama/ollama/issues/7400)

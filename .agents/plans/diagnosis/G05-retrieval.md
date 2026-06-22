# Diagnosis: G05-retrieval

Coverage: Read fully (every line) — `__init__.py`, `models.py`, `fusion.py`, `chunking.py`, `vector.py`, `engine.py`, `lexical.py`, `embedding.py`, `evidence.py`, `orchestrator.py`, `providers.py`, `query_expander.py`, `router.py`, `expansion.py`, `materializer.py`, `evaluation.py`. Cross-checked `backend/src/curator/search.py::query` signature and `db.py` helper signatures (`get_search_document`, `get_search_chunk`, `list_search_chunks_for_doc`, `has_search_embeddings`) for contract correctness. Spec context from CLAUDE.md storage/curation invariants.

## Findings

### [G05-retrieval-1] (a) S2 — Reranker score/passage length mismatch silently drops candidates
- Loc: backend/src/curator/retrieval/engine.py:160 (`zip(fused, raw, rrf_norm)`)
- Evidence: `_rerank` calls `raw = self.reranker.score(question, passages)` then `for hit, ce, rn in zip(fused, raw, rrf_norm)`. `zip` truncates to the shortest iterable. If a reranker returns fewer scores than passages (partial failure, a model that skips empty passages, or `LlamaCppReranker.score` swallowing an item), the tail of `fused` is silently discarded from the blended ranking rather than retaining its RRF order. There is no length assertion, unlike `embedding._embed_inputs`/`OllamaEmbedder.embed` which DO raise on count mismatch.
- Fix sketch: Assert `len(raw) == len(passages)` and on mismatch fall back to `no_rerank` (return RRF order) as the engine already does for exceptions; or pad/zip-longest with the RRF score so no candidate is dropped.
- Blast radius: Hybrid answer path only (rerank=True, mode=hybrid). Wrong/short result set, lost recall; no crash.
- Suggested PR: "fix(retrieval): guard reranker score-count mismatch, degrade to no_rerank"

### [G05-retrieval-2] (a) S3 — `rerank_score`/`fallback_mode` no_rerank marker is lost when already in lex fallback
- Loc: backend/src/curator/retrieval/engine.py:280 and :306
- Evidence: At :280 `fallback_mode = fallback_mode or "no_rerank"`. If the vector layer was unavailable, `fallback_mode` is already `"lex"`, so `or` keeps `"lex"` and the no_rerank state is never recorded in `fallback_mode` (the warning is still appended, but the machine-readable mode is not). Consequently at :306 `not fallback_mode.startswith("no_rerank")` is `True` even though reranking actually failed, so `EngineHit.rerank_score` is populated with the RRF-order `final` score, mislabeling an un-reranked hit as reranked. The two degradations (lex + no_rerank) cannot be represented simultaneously by a single string field.
- Fix sketch: Track rerank degradation in a separate boolean (e.g. `rerank_applied`) instead of overloading `fallback_mode`; set `rerank_score` from that flag.
- Blast radius: Trace/observability + `rerank_score` field correctness; ranking itself unaffected. Low.
- Suggested PR: "fix(retrieval): represent lex + no_rerank degradations independently"

### [G05-retrieval-3] (a) S3 — `rerank_score` records the blended score, not the cross-encoder score
- Loc: backend/src/curator/retrieval/engine.py:162,164,306
- Evidence: `_rerank` computes `blended.append((hit, final, float(ce)))` capturing the raw CE score as the 3rd tuple element, but then returns `[(h, s) for h, s, _ in blended]` — discarding `ce`. Back in `search`, `rerank_score=final` (the RRF+CE blend), so the field named `rerank_score` never carries the actual reranker output. The raw CE signal that was deliberately preserved is thrown away.
- Fix sketch: Return the raw `ce` alongside `final` from `_rerank` and assign it to `EngineHit.rerank_score`; keep `score` as the blended value.
- Blast radius: Observability/dashboard semantics only. Low.
- Suggested PR: folds into G05-retrieval-2 PR.

### [G05-retrieval-4] (h) S2 — Chunk overlap can advance the buffer past `target_tokens`, producing unbounded chunk growth / non-termination risk on degenerate input
- Loc: backend/src/curator/retrieval/chunking.py:84-110 (`_flush` overlap carry + main loop)
- Evidence: `_flush` carries an overlap tail of whole sentences. The tail loop keeps inserting until `tail_tok + st > overlap_tokens and tail` — i.e. it always keeps at least one sentence even if that single sentence alone exceeds `overlap_tokens` (or even `target_tokens`). After flush, `buf_tok` is reset to `tail_tok`, which can already be ≥ `target_tokens`. The next appended sentence then re-triggers a flush whose tail is again that same large sentence, so the same giant sentence can be re-emitted across consecutive chunks. For a document that is one very long sentence with no terminators, `_split_sentences` returns it whole and it is never sub-split (no hard-window fallback despite the module docstring claiming "only falling back to hard windows for pathological undelimited text" — there is NO hard-window code path). `max_tokens` is therefore not actually enforced for a single oversized sentence.
- Fix sketch: Cap the overlap tail to never exceed `overlap_tokens` even if it means an empty tail; add the promised hard-window splitter for a single sentence exceeding `max_tokens`.
- Blast radius: Embedding corpus quality (oversized chunks blow the embedder context / wash out centroids); duplicated chunk text inflates the index. Affects pathological inputs (code blocks, undelimited CJK, tables). Medium.
- Suggested PR: "fix(retrieval): enforce max_tokens with hard-window fallback in chunker"

### [G05-retrieval-5] (g) S2 — `vector_search` loads the ENTIRE embedding table into memory on every probe (no families filter pushed to SQL)
- Loc: backend/src/curator/retrieval/vector.py:47-62; amplified by engine.py:222,257-264
- Evidence: `vector_search` runs `SELECT ... FROM search_embeddings JOIN search_chunks WHERE provider=? AND model=?` with NO `record_type`/family filter in SQL, fetches all rows, concatenates all vector BLOBs into one matrix, and only filters by `families` in Python AFTER the matmul. The hybrid engine calls `_vector_list` once for the raw probe (`:222`) plus once per expansion vec text (`:257`) plus once for HyDE (`:262`) — each call re-reads and re-materializes the full embedding matrix from SQLite (3–5× full-table scans + 3–5× full matmuls per query). The docstring's "<50 ms" assumes one pass; expansion multiplies it.
- Fix sketch: Push `families` into the SQL WHERE (`c.record_type IN (...)`); cache the loaded matrix/ids for the lifetime of a single `search()` call so the raw + expansion + HyDE probes reuse one in-memory matrix instead of reloading.
- Blast radius: Query latency on every hybrid query, scaling linearly with corpus and expansion count. Medium-high as corpus grows toward the documented ~50k-chunk ceiling.
- Suggested PR: "perf(retrieval): reuse embedding matrix across probes; push family filter to SQL"

### [G05-retrieval-6] (g) S2 — `embed_corpus` reads all chunk rows into memory and never reuses the already-loaded `existing` embeddings; partial batch failure mislabels fingerprint
- Loc: backend/src/curator/retrieval/embedding.py:124-165
- Evidence: (1) `conn.execute("SELECT chunk_id, text, input_hash, provenance_json FROM search_chunks ...").fetchall()` loads every chunk row into memory at once — fine for personal scale but unbounded. (2) `search_embedded_count` is set to `str(embedded + skipped)` (:165), which only counts chunks touched this run, not the true corpus embedding count if some batches failed (`failures` chunks silently excluded from the count meta, so the meta undercounts/overcounts depending on prior state). (3) The fingerprint is written `if embedded or skipped` (:164) even when there were also failures, so a partially-failed embed pass is recorded as if the vector space is fully consistent — a later `_vectors_available` check returns True and the engine will silently search an incomplete vector index with no warning.
- Fix sketch: Iterate chunk rows in a server-side cursor / batched fetch; record `failures` in index meta and gate the "ready" fingerprint on `failures == 0` (or emit a `partial` fingerprint state so the engine can warn).
- Blast radius: Silent partial-index correctness (recall holes) after a flaky embedder run. Medium.
- Suggested PR: "fix(retrieval): gate embed fingerprint on zero failures; record failure count"

### [G05-retrieval-7] (b) S3 — Two divergent stopword lists and two near-identical seed-term tokenizers
- Loc: backend/src/curator/retrieval/evidence.py:22-26 (`_STOP`) + :183-191 (`seed_terms`) vs backend/src/curator/retrieval/lexical.py:22 (imports `_STOP` from evidence) + lexical `parse_query` term filtering; `_report_items` (evidence.py:301) re-implements the same tokenize+stopword+len filter inline a third time.
- Evidence: `lexical.py` reaches into `evidence.py` for the private `_STOP` set (`from .evidence import _STOP`), coupling the lexical layer to the evidence layer (wrong dependency direction — lexical is P4, evidence is higher). `seed_terms` (evidence) uses `len(tok) <= 3` while `parse_query` (lexical) uses `len(word) <= 2`; `_report_items` uses `len(t) > 2`. Three slightly different "too short" thresholds and three copies of the regex `[A-Za-z][A-Za-z0-9+\-]*`.
- Fix sketch: Move `_STOP` and a single `extract_terms()` helper into a low-level module (e.g. `lexical.py` or a new `text_utils`) and have evidence import from it; unify the min-length threshold.
- Blast radius: Maintainability + subtle inconsistency in which terms drive entity seeding vs report scoring. Low correctness risk now.
- Suggested PR: "refactor(retrieval): single source for stopwords + term extraction"

### [G05-retrieval-8] (c) S2 — Broad `except Exception` masks all failures across the embed/expand/rerank/search paths
- Loc: engine.py:115, 154; embedding.py:145; query_expander.py:152,157,177,185,197,202,206; providers.py:211,295; orchestrator.py:35; expansion.py:100
- Evidence: Nearly every external-call boundary catches bare `Exception` and silently returns an empty/degraded result. While "degrade gracefully" is the documented design, several of these swallow with NO logging and NO warning surfaced: e.g. `engine.py:115` `_vector_list` returns `[], {}, None` on any embedder exception with no warning appended (the caller cannot distinguish "embedder threw" from "no hits"), and `_rerank` (:154) returns no_rerank but the warning text is generic. `embed_corpus` keeps `warning` only for the LAST failing batch (overwrites prior). A genuine config/programming bug (e.g. wrong dim, JSON shape change) is indistinguishable from a transient transport failure.
- Fix sketch: Narrow to `(httpx.HTTPError, ValueError, RuntimeError)` where the failure modes are known; log at debug/warning; surface a structured warning from `_vector_list` so the trace shows "embedder raised" distinctly from "no embeddings".
- Blast radius: Diagnosability — masks real bugs as graceful degradation. Medium.
- Suggested PR: "fix(retrieval): narrow exception handling + surface embed/vector failures in trace"

### [G05-retrieval-9] (a) S3 — `_report_score` tie-break adds raw `rank` which can dominate the term-overlap signal
- Loc: backend/src/curator/retrieval/evidence.py:282-289
- Evidence: `return overlap / len(query_terms) + rep.get("rank", 0.0) * 0.01`. `overlap/len(query_terms)` is in [0,1]. `rank * 0.01` is unbounded — community report `rank` (a 1–10 importance score per the materializer provenance, but no upper bound enforced) at e.g. rank 100 contributes 1.0, equal to a perfect term match. The comment says it is a "query-relevance score" but a high standalone rank can outrank a strictly more query-relevant report. Also when `query_terms` is empty the function returns raw `rank` (line 285 path) on a totally different scale than the normal path, so empty-query and non-empty-query orderings are incomparable.
- Fix sketch: Normalize `rank` to [0,1] (divide by max rank) before the 0.01 weight, or clamp; make the empty-query branch consistent.
- Blast radius: Global-route report selection ordering (top-10 cut). Medium for global answers.
- Suggested PR: "fix(retrieval): bound report rank tie-break in _report_score"

### [G05-retrieval-10] (a) S2 — `explore` route re-resolves policy by re-parsing curate.yml, diverging from the policy used to build the pack
- Loc: backend/src/curator/retrieval/orchestrator.py:220 (`policy, _ = _resolve_policy(request.workspace_path)`)
- Evidence: `run()` already obtained `spec_hash` from `context_pack["snapshot"]["policy_hash"]` and the comment at :80-81 explicitly says "Reuse the policy hash context_fetch already resolved instead of re-parsing curate.yml a second time." But `_run_explore_from_context` re-calls `_resolve_policy(request.workspace_path)` to get `policy.max_explore_followups` and `policy.workspace_id`, re-parsing curate.yml a second time anyway — defeating the stated optimization and risking a TOCTOU mismatch if curate.yml changed between `context_fetch` and here. `_resolve_policy` also silently swallows load errors (`except Exception: spec = None`) and falls back to default policy, so a malformed curate.yml during explore silently changes `max_explore_followups`/`workspace_id` vs what built the pack.
- Fix sketch: Pass the resolved policy (or at least `max_explore_followups` + `workspace_id`) through the context_pack snapshot so explore reuses it; don't re-parse.
- Blast radius: explore route only; potential inconsistent follow-up budget / wrong workspace_id on insight candidates. Medium.
- Suggested PR: "fix(retrieval): thread resolved policy into explore phase, stop re-parsing curate.yml"

### [G05-retrieval-11] (h) S3 — `_span_items` ordering depends on `get_source_spans_by_ids` return order, and silently drops missing spans
- Loc: backend/src/curator/retrieval/evidence.py:256-279
- Evidence: `span_by_id = {span["id"]: span ...}` then `spans = [span_by_id[span_id] for span_id in span_ids if span_id in span_by_id]`. Spans whose id is not returned by the DB (deleted/retired between graph build and query) are silently filtered out with no warning — an evidence item the entity claimed to back simply vanishes. For source-section route this means a span listed by `list_source_spans` but not re-fetchable yields a silent gap. No `evidence_status` degradation marker is emitted for the dropped span (unlike the stale-text path which is handled).
- Fix sketch: Count and warn on dropped spans (`f"{n} span(s) unresolved"`), mirroring the `omitted_counts` pattern used elsewhere.
- Blast radius: Silent evidence loss on a desynced DB. Low-medium.
- Suggested PR: "fix(retrieval): warn on unresolved span ids in _span_items"

### [G05-retrieval-12] (b) S3 — Redundant `llama_cpp` re-import / dynamic `__import__` in providers
- Loc: backend/src/curator/retrieval/providers.py:141,147 and :233,242
- Evidence: `LlamaCppEmbedder.__init__` does `from llama_cpp import Llama` then `llama_cpp = __import__("llama_cpp")` — two imports of the same module. `LlamaCppReranker.__init__` inlines `getattr(__import__("llama_cpp"), "LLAMA_POOLING_TYPE_RANK", 4)`. The `__import__` string form is non-idiomatic and defeats static analysis; the embedder already has `Llama` so it could `import llama_cpp` once.
- Fix sketch: `import llama_cpp` once at top of each `__init__` and reference `llama_cpp.Llama` / `llama_cpp.LLAMA_POOLING_TYPE_*`.
- Blast radius: Style/maintainability only. Trivial.
- Suggested PR: trivial nit — fold into a cleanup PR.

### [G05-retrieval-13] (a) S3 — `min_score` filter falls back to a single hit, contradicting "never returns empty" only for the borderline case
- Loc: backend/src/curator/retrieval/engine.py:312-314
- Evidence: `if min_score > 0: kept = [h for h in hits if h.score >= min_score]; hits = kept or hits[:1]`. When `kept` is empty this returns `hits[:1]` — the single top hit even though it failed the threshold. That is intentional per the docstring, BUT the blended `score` here is the rerank-blend (or RRF) which is NOT on a 0–1 scale (the search.py docstring itself warns `min_score` is "advisory" and native scores aren't 0–1). So any caller passing a meaningful `min_score>0` (e.g. an MCP/plugin caller expecting cosine-like thresholds) will get near-random filtering. evidence.py wisely passes `min_score=0.0`, but the parameter is still exposed and misleading.
- Fix sketch: Document loudly that `min_score` only applies to reranked cosine-like scores, or remove the param from the public `search.query` surface; alternatively normalize scores before thresholding.
- Blast radius: External callers (MCP/plugin) only. Low.
- Suggested PR: "docs(search): clarify min_score is advisory / non-normalized" (+ optional removal).

### [G05-retrieval-14] (h) S3 — `LexicalQuery.is_cjk` uses a narrower CJK range than the materializer/chunker, risking trigram-index desync
- Loc: lexical.py:26 (`[぀-ヿ㐀-鿿가-힯]`) vs materializer.py:18 / chunking comments (`[぀-ヿ㐀-鿿가-힯]`)
- Evidence: lexical's `_CJK_RE` literal range `㐀-鿿` is U+3400–U+9FFF (CJK ext-A + unified), while materializer's `_CJK_RE` is `㐀-鿿` — these match. But lexical's hiragana/katakana range `぀-ヿ` is U+3040–U+30FF and materializer uses `぀-ヿ` — match. They are actually equivalent; however the language tag in materializer is set to `"ko"` for ALL CJK (`_language`), mislabeling Japanese/Chinese documents as Korean. The trigram index is shared so retrieval still works, but any per-language logic keyed on the `language` column is wrong.
- Fix sketch: Either drop the misleading `"ko"` label (use `"cjk"`) or detect script properly; verify no downstream code branches on `language == "ko"`.
- Blast radius: Only if `language` column is consumed elsewhere. Low.
- Suggested PR: "fix(retrieval): stop labeling all CJK as 'ko' in materializer".

### [G05-retrieval-15] (g) S3 — `materialize_search_documents` loads all six full tables into memory and re-upserts every doc unconditionally
- Loc: backend/src/curator/retrieval/materializer.py:113-318
- Evidence: `db.clear_search_corpus(db_path)` then `SELECT *` on `sources`, `source_spans`, `knowledge_units`, `graph_entities`, `graph_relations`, `community_reports`, `synthesis_nodes` — all `.fetchall()` into Python lists, then a per-row `db.upsert_search_document` (one INSERT per record, no executemany). The `content_hash`/`dependency_hash` are computed per row but the corpus is fully cleared first, so the hashes provide no incremental-skip benefit here (full rebuild every time). For a large vault this is O(N) Python-side INSERTs with per-call connection overhead inside `upsert_search_document`.
- Fix sketch: Batch the upserts (executemany / single transaction) and/or make materialization incremental by diffing `content_hash` against the existing corpus instead of `clear_search_corpus` + full rebuild.
- Blast radius: `wiki reindex` / compile latency, scales with corpus. Medium at scale.
- Suggested PR: "perf(retrieval): batch + incrementalize search document materialization"

### [G05-retrieval-16] (a) S3 — `EvidencePack.evidence_block` marker-budget worst case can still overflow then hard-slices mid-marker
- Loc: backend/src/curator/retrieval/models.py:94-134
- Evidence: The marker budget reserves `len(marker_for(total)) + len(sep)` up front, but the actual marker uses `marker_for(omitted)` where `omitted <= total`, so the reserved budget is an upper bound (good). However the final `return block[:max_chars]` can cut the omission marker mid-text when `max_chars` is smaller than the marker — silently truncating the very signal that says content was omitted, with no guarantee the truncated string is still recognizable. This is the documented "degenerate case," but a truncated marker like `[3 items omi` is worse than no marker.
- Fix sketch: When `max_chars < len(marker)`, return just the marker (or an ellipsis) rather than a sliced item+partial-marker; the marker is the priority signal.
- Blast radius: Only pathologically small `max_chars` (default 16000). Very low.
- Suggested PR: trivial — fold into a cleanup PR.

### [G05-retrieval-17] (a) S2 — `_run_answer_from_context` overwrites `source_span_ids` with prompt output even when the model returns an empty list
- Loc: backend/src/curator/retrieval/orchestrator.py:145-146
- Evidence: `if hasattr(run.parsed, "source_span_ids"): result.source_span_ids = getattr(run.parsed, "source_span_ids") or []`. If the LLM answer parses successfully but returns NO span ids (model omitted citations), this REPLACES the retrieved `result.source_span_ids` (set from the evidence pack at construction) with `[]`, erasing all retrieval provenance for a successful answer. The failure branch (:147-156) was carefully written to preserve provenance on synthesis failure, but the success-with-no-citations path silently discards it — the opposite intent. `_update_context_trace_after_synthesis` then persists `cited_source_span_ids: []` and recall metrics read 0.
- Fix sketch: Only overwrite when the model returned a non-empty subset, or intersect the model's cited ids with the retrieved `valid_spans` and keep the retrieved set as the provenance floor.
- Blast radius: local/global answer routes whenever the model under-cites. Provenance loss + metric corruption. Medium-high.
- Suggested PR: "fix(retrieval): don't erase retrieval provenance when answer cites no spans"

## Positives (keep / do-not-break)
- RRF fusion (`fusion.py`) is clean, rank-only, fully deterministic, and carries a per-list contribution trace — exactly the right design for the BM25-vs-cosine scale mismatch. Do not "normalize scores" during a refactor.
- Explicit, layered graceful degradation in `engine.search` (vector → lex, reranker → no_rerank) with distinct trace warnings is a genuine strength; the `_vectors_available` distinction (no embedder vs corpus-not-embedded vs unreachable) is well thought out.
- `_apply_policy_scope` (evidence.py) correctly refuses to mutate `source_span_ids` of multi-source items and drops the whole item to avoid leaking excluded sources — a subtle, correct provenance-safety decision. Preserve the "strict, never trim" semantics.
- `vector.py` collapse-to-best-chunk-per-doc + L2-normalized dot-product cosine is correct and matches `pack_vector`. Keep the normalization contract paired between `pack_vector` and `vector_search`.
- `evaluation.py` is provider-free and deterministic (citation correctness requires span ⊆ authoritative spans) — good test infrastructure; do not couple it to live providers.
- Duck-typed `Embedder`/`Reranker` Protocols make the engine testable with mocks; keep the duck-typing seam.

## Open questions for the human
- Is `min_score` on the public `search.query` surface actually used by any MCP/plugin caller with a non-zero value? If yes, finding #13 is higher severity because the score scale is non-normalized.
- Is the `language` column written by the materializer (`"ko"` for all CJK) consumed anywhere (ranking, prompt language selection)? Determines severity of #14.
- For #17: is the intended contract that a successful answer with zero cited spans should keep the retrieval provenance, or genuinely report zero citations? The asymmetry vs the failure branch suggests a bug, but please confirm the desired QTR semantics.
- Does any reranker implementation legitimately return fewer scores than passages (e.g. skipping empty passages)? Confirms whether #1 is reachable in practice or purely defensive.

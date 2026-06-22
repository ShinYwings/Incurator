# Diagnosis: G06-query-search-context

Coverage:
- `backend/src/curator/query.py` (733 lines) — read fully.
- `backend/src/curator/search.py` (372 lines) — read fully.
- `backend/src/curator/context_service.py` (1121 lines) — read fully.
- Neighbor context verified by targeted reads/greps: `db.insert_query_trace` / `get_query_trace*` (db.py:4557-4650), `retrieval/models.py` (QueryRequest.working_query), callers in `cli.py`, `mcp_server.py`, `plugin_api.py`, and tests (`test_query_source_links.py`, `test_plan_f_context_service_contract.py`).

## Findings

### [G06-query-search-context-1] (d) S1 — ~230 lines of dead, unreachable legacy code after an unconditional `return` in `run_query`
- Loc: backend/src/curator/query.py:496-733
- Evidence: `run_query` validates the route then `return _run_query_orchestrated(...)` at line 496-501. Every statement from line 503 (`callbacks.on_start(question, mode)`) through line 733 is unreachable — the legacy translate→intent→search→synthesize→stream pipeline, including the nested helpers `_search_for` (584), `_keyword_fallback` (527), the multi-stage fallback search (601-621), the `client.unload()` VRAM guard (572), and the entire `chat_stream` synthesis/error-handling block (681-716). None of it can ever execute. The function's own parameters `mode`, `limit`, `min_score`, `rerank`, `temperature`, `scope`, `classify_intent_first`, `query_boost_terms` are now all silently ignored — callers passing them (cli.py:4951) believe they take effect.
- Fix sketch: Delete lines 503-733 and the now-unused params, OR (if the orchestrator path is provisional) gate it behind a flag. Decide deliberately — a future refactor must NOT "revive" this block by reordering. Also remove module-level constants only used by the dead block (`MAX_SYNTHESIS_SOURCE_CHARS` is used by `_build_synthesis_user_prompt` which is test-only; see finding 2).
- Blast radius: High surface, low runtime risk (already dead). Removing it changes nothing at runtime but eliminates a major source of confusion and the false impression that `mode/scope/limit/rerank` are honored.
- Suggested PR: "fix(query): remove unreachable legacy run_query body and ignored params"

### [G06-query-search-context-2] (d/e) S2 — `_build_synthesis_user_prompt`, `SYNTHESIS_SYSTEM_PROMPT`, `MAX_SYNTHESIS_SOURCE_CHARS` are only reachable from dead code + tests
- Loc: backend/src/curator/query.py:33,122-144,183-254
- Evidence: `_build_synthesis_user_prompt` is called only at query.py:665 (inside the dead block) and from `backend/tests/test_query_source_links.py:68,80`. `SYNTHESIS_SYSTEM_PROMPT` (122) and `MAX_SYNTHESIS_SOURCE_CHARS` (33) are referenced only inside the dead block. The real synthesis prompt now lives in `retrieval`/`prompts`. So these are kept alive only by a test that exercises orphaned code — a test that no longer reflects the production answer path.
- Fix sketch: When removing the dead block (finding 1), decide the fate of these symbols. If synthesis prompting fully moved to `retrieval`, delete them and their test; if still canonical, wire them into the orchestrator. Do not leave test-only-live prompt logic.
- Blast radius: Medium — touches a test file. Low runtime risk.
- Suggested PR: same PR as finding 1 (coordinate with docs_sync_manager + the test).

### [G06-query-search-context-3] (h) S1 — `_append_context_action` resets the trace `created_at` on every expand/verify/feedback (timestamp + ordering corruption)
- Loc: backend/src/curator/context_service.py:1104-1121 → db.py:4581-4596
- Evidence: `context_expand`, `context_verify`, and `context_feedback` all call `_append_context_action`, which re-persists the whole trace via `db.insert_query_trace(...)`. That function does `INSERT OR REPLACE INTO query_traces (..., created_at) VALUES (..., _now_iso())` (db.py:4587,4595) — it always stamps the current time and never preserves the original `created_at`. So any follow-up action on a pack silently rewrites the trace's creation timestamp. `list_query_traces` orders by `created_at DESC` (db.py:4621), so expanded/verified traces jump to "newest", and any latency/age analytics keyed on `created_at` are wrong.
- Fix sketch: Either add a `created_at` passthrough param to `insert_query_trace` and have `_append_context_action` forward `trace["created_at"]`, or switch the action-append to an `UPDATE` that touches only `retrieval_trace_json` (and not `created_at`). Prefer the UPDATE seam so re-persisting a trace can never clobber immutable columns.
- Blast radius: Affects trace history ordering, audit timestamps, and any TTL/age logic. Cross-module (context_service + db).
- Suggested PR: "fix(context): preserve query-trace created_at across action appends"

### [G06-query-search-context-4] (a) S2 — `_append_context_action` re-persist drops `latency_ms` accuracy and assumes trace fields are always present
- Loc: backend/src/curator/context_service.py:1104-1121
- Evidence: The re-insert forwards `trace["latency_ms"]`, `trace["prompt_trace_ids"]`, `trace["insight_candidate_ids"]`, etc. via direct dict indexing (`trace["..."]`). `_decode_query_trace` (db.py:4601) does provide these keys, so the indexing is currently safe — but it is brittle: any trace row not produced by the standard decoder (or a schema addition) raises `KeyError` mid-operation, after the in-memory `actions` list was mutated but before persistence, leaving the caller with a half-applied expansion. There is no transaction wrapping the read-modify-write.
- Fix sketch: Use `.get(...)` with defaults for the forwarded fields, and wrap the read-modify-write of a trace in a single DB transaction (or an atomic UPDATE) so a mid-write failure cannot leave the in-memory/DB state diverged.
- Blast radius: context_expand/verify/feedback robustness. Localized.
- Suggested PR: "fix(context): harden trace re-persist (defaults + atomic update)"

### [G06-query-search-context-5] (h) S2 — Read-modify-write of a trace's `actions` list is racy under concurrent context_* calls
- Loc: backend/src/curator/context_service.py:1074-1121 (and callers 834-850, 902-908, 1026-1032)
- Evidence: Each `context_expand`/`context_verify`/`context_feedback` does: `get_query_trace(...)` → mutate `actions`/`selected_items` in Python → `insert_query_trace(... INSERT OR REPLACE ...)`. Two concurrent operations on the same `pack_id` (e.g. an MCP client firing `context_expand` twice, or expand+feedback) read the same base trace and the second writer overwrites the first's appended action — lost-update. `INSERT OR REPLACE` makes the loser silently vanish (no conflict raised). The snapshot guard (`expected_snapshot_id`) does NOT protect against this: snapshot is about source-epoch staleness, not trace-row concurrency.
- Fix sketch: Serialize per-pack mutations (e.g. an `UPDATE ... WHERE trace_id=? AND <version/action_count unchanged>` optimistic-concurrency check that returns rows-affected, retrying or returning a conflict on 0), or take a write lock. At minimum document the single-writer assumption.
- Blast radius: Multi-client MCP usage. Data-loss class, but only under concurrency.
- Suggested PR: "fix(context): optimistic-concurrency guard on trace action append"

### [G06-query-search-context-6] (a) S3 — `context_expand` "no expansion handles matched" warning is computed from the wrong variable
- Loc: backend/src/curator/context_service.py:863
- Evidence: In the success-return, `"warnings": [] if matched else ["no expansion handles matched"]`. `matched` (line 764) is the set of omitted candidates whose handle was requested. But the empty-result early return at 778-801 already handles the "nothing matched / already selected" case with its own warning. By the time control reaches line 852, `selected` or `omitted` is non-empty, so `matched` is necessarily truthy — the `else` branch at 863 is effectively dead, and worse, if a handle matched an item that went entirely to `omitted` (budget exhausted), the response carries no warning even though zero items were added (`expansion_refused` is populated instead). The warning logic is inconsistent with the `selected`/`omitted` reality.
- Fix sketch: Base the warning on whether anything was actually selected (`[] if selected else ["expansion refused: budget exhausted"]`) and drop the unreachable `matched` ternary, or remove the redundant branch entirely since 778 covers the no-match case.
- Blast radius: Cosmetic/contract — affects MCP client messaging only. Low.
- Suggested PR: "fix(context): correct context_expand warning to reflect selected vs refused"

### [G06-query-search-context-7] (a) S3 — `_build_retrieval_trace` candidate_count can double-count budget-omitted items
- Loc: backend/src/curator/context_service.py:120-140, 566-621
- Evidence: `candidate_count = len(pack.items) + sum(pack.omitted_counts.values())` (line 134). In `context_fetch`, `pack.items` is the full retrieved set; budget then splits it into `selected_items` + `budget_omitted_items` (566). The budget-omitted items are still counted inside `len(pack.items)`, AND `omitted_counts["budget"]` is added separately (576-579). So when the trace is built with the post-budget `omitted_counts` (which now includes the `budget` key), `candidate_count = len(pack.items) + retrieval_omitted + budget_omitted`, over-counting by the number of budget-omitted items (they are part of `pack.items`). The displayed candidate total exceeds reality.
- Fix sketch: Compute `candidate_count` from a single source of truth (e.g. `len(pack.items) + retrieval-stage omissions only`), and exclude the `budget` synthetic key from that sum, or compute candidates as `selected + all-omitted` consistently.
- Blast radius: Trace analytics only. Low.
- Suggested PR: "fix(context): stop double-counting budget-omitted items in candidate_count"

### [G06-query-search-context-8] (g) S2 — `search_source_pages` re-parses every tracked source file on every call (no index, full scan)
- Loc: backend/src/curator/search.py:297-372
- Evidence: It selects all `sources` rows, then for each row calls `parsers.parse(file_path)` (line 333) — a full PDF/HTML/text parse — and lexically scans the parsed text in Python. There is no caching and no early termination: a provenance lookup over N tracked PDFs re-parses all N files from disk every invocation, O(total corpus bytes) per query. For a vault with many/large PDFs this is a heavy synchronous hot path.
- Fix sketch: Use the already-materialized `source_spans` / FTS index in `state.sqlite` (which `update_index` builds) for provenance lexical lookups instead of re-parsing originals, or cache parsed results keyed by content hash. If raw-file fidelity (PDF page numbers) is truly required, restrict parsing to candidate sources pre-filtered by an FTS hit rather than parsing all.
- Blast radius: Performance on provenance lookups; correctness unaffected. Medium.
- Suggested PR: "perf(search): back search_source_pages with the DB index instead of full re-parse"

### [G06-query-search-context-9] (c) S3 — Broad `except Exception: pass` swallows parse and VRAM-unload failures silently
- Loc: backend/src/curator/search.py:36-41 (`_free_ollama_vram_before_llama_cpp`), search.py:332-335 (`parsers.parse`), search.py:334; query.py:297-298 (`translate_to_english`), query.py:324-335 (`classify_wiki_topic`)
- Evidence: `_free_ollama_vram_before_llama_cpp` wraps the whole unload in `except Exception: pass` (40-41) — a genuinely failing unload (leaving VRAM occupied so the subsequent llama-cpp load OOMs) is invisible. `search_source_pages` does `except Exception: continue` (334) on parse, so a systematically broken parser silently yields zero provenance hits with no signal. `translate_to_english` and `classify_wiki_topic` swallow all exceptions into silent fallbacks. These are defensible as best-effort, but none log even at debug level, so real misconfiguration is undiagnosable.
- Fix sketch: Narrow to expected exception types where possible and add a debug/warn log in the `except` so operators can see why translation/parse/unload degraded. Do not change control flow.
- Blast radius: Observability only. Low.
- Suggested PR: "chore(search/query): log best-effort failures instead of silent swallow"

### [G06-query-search-context-10] (f) S3 — `query.py` docstrings/comments describe behavior that no longer runs
- Loc: backend/src/curator/query.py:467-483 (`run_query` docstring describes `scope`/`classify_intent_first`/`mode` semantics), 192 (`_build_synthesis_user_prompt` "for Qwen3"), 70 ("v0.3.1 curation-native trace fields")
- Evidence: The `run_query` docstring still documents `scope` layer filtering, intent classification, and `mode` — all implemented only in the unreachable block (finding 1). A reader/maintainer trusting the docstring will believe `scope="atoms"` filters retrieval, but it is silently ignored. The `_build_synthesis_user_prompt` docstring hardcodes "for Qwen3", coupling a generic prompt builder to one model name.
- Fix sketch: When finding 1 is resolved, rewrite the `run_query` docstring to describe only the orchestrated behavior and either re-plumb `scope`/`mode` into the orchestrator or remove them from the signature. Drop the model-specific "Qwen3" wording.
- Blast radius: Docs/code drift; misleads maintainers. Low.
- Suggested PR: bundle with finding 1.

### [G06-query-search-context-11] (a) S3 — `min_score` default mismatch between `query.run_query` (0.6) and `search.query` (0.0) is now masked but latent
- Loc: backend/src/curator/query.py:455 (`min_score: float = 0.6`) vs search.py:177 (`min_score: float = 0.0`)
- Evidence: `run_query` advertises a default `min_score=0.6`, but because the live path is `_run_query_orchestrated` (which never forwards `min_score` to `search.query`), the 0.6 is silently dropped. `search.query`'s own default is 0.0. If a caller relies on `run_query(min_score=...)` to filter, it has no effect on the orchestrated path. This is a contract lie introduced by finding 1.
- Fix sketch: Either thread `min_score` through `QueryRequest`/orchestrator or remove it from `run_query`'s signature so callers stop passing a no-op. Reconcile the default with the engine.
- Blast radius: API contract clarity. Low.
- Suggested PR: bundle with finding 1.

## Positives (keep / do-not-break)
- `_LEGACY_SCHEME_RE` (query.py:35-40): the deliberate string-concatenation construction of the retired-scheme matcher (so the literal never appears in source) and the explicit narrowness (won't strip `http(s)://`/`obsidian://`) is well-reasoned; keep the comment and the narrow regex.
- `_node_path_from_target` (query.py:262-269): correctly unwraps `[[...]]` before stripping `|alias` and `.md`, with a precise comment about ordering. Keep.
- ContextService snapshot/optimistic-concurrency design (`_snapshot`, `expected_snapshot_id` guards in fetch/expand/verify, `_conflict_response`): the source-epoch hashing (`_source_epoch`, `_hash_epoch_rows`) is a clean staleness contract — preserve the snapshot semantics across any refactor.
- `_budget_payloads` `already_used` seeding (context_service.py:475-509): the cumulative-budget reasoning (so successive `context_expand` calls don't each get a fresh full window) is correct and well-documented; do not regress to per-call budgets.
- Append-only, quarantined feedback model (`context_feedback`, 923-1047): feedback never mutates ranking/truth/source; `new_insight` only enqueues a pending candidate. This isolation is a strong invariant — keep it.
- Graceful-degradation contract in `search` (`is_available()` always True; vector/rerank degrade) is clearly documented and consistent.
- `_admit_route` (context_service.py:43-58): route admission runs BEFORE `build_evidence`, so a rejected route never spawns a divergent retrieval path — good seam.

## Open questions for the human
- Is `_run_query_orchestrated` intended to be the permanent path, making the legacy `run_query` body (findings 1,2,10,11) safe to delete outright? Or is the orchestrator a staged rollout where the legacy block must be revived behind a flag? This decides whether to delete vs. gate.
- Should `scope` (layer filtering) and `min_score`/`mode`/`rerank` be re-plumbed into `QueryOrchestrator`/`QueryRequest`, or formally dropped from `run_query`'s public signature? Callers (cli.py:4951) currently pass them as no-ops.
- For `context_*` re-persist (findings 3,4,5): is concurrent access to a single `pack_id` actually possible in the MCP server (single-threaded request loop vs. async)? That determines whether finding 5 is S2 or downgradeable.
- `search_source_pages` (finding 8): is the raw-file re-parse needed for PDF page-number fidelity that the DB index can't provide, or can it move fully to the materialized index?

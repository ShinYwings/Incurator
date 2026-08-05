# retrieval_context Proposal: Five Retrieval/ContextService Contract Defects
Date: 2026-08-04 | Agent Persona: Retrieval Contract Auditor

Scope audited: `backend/src/curator/retrieval/{engine,evidence,orchestrator,fusion,expansion,query_expander}.py`,
`backend/src/curator/context_service.py`, `backend/src/curator/plugin_api/context.py`,
`backend/src/curator/commands/plugin.py`.
Specs read (ranges only): SYSTEM_BEHAVIOR §12/§12.1 (1068–1109), §28 (2812–2914),
§30.2–§31.8 (3113–3407), SEARCH_ENGINE_SCHEMA §8 (261–340).
CAND-04 (StructuredLocator `exact` fabrication) is excluded by instruction and is
NOT re-reported below, even though `_item_locator` was read in passing.

> **Second-pass consolidation note (same date, same persona).** This document was
> re-audited from scratch against the same spec ranges. RC-1 through RC-4 were
> re-derived independently and are confirmed verbatim — the code, line numbers, and
> failure scenarios below were re-read and still hold at the current working tree.
> Two changes were made on the second pass, both additive:
>
> 1. **RC-2 severity raised P2 → P1.** Rationale in the finding body: the check is
>    not merely weak, it is *structurally incapable* of ever firing, so §31.3's
>    "does not mix epochs silently" has no implementation at all on the expand and
>    verify paths, and the client has no independent way to detect the staleness.
> 2. **RC-5 broadened** from "the `policy` block is missing" to the full class of
>    *contract fields promised but never written*, adding the §31.5 evidence-item
>    field gaps and the `layer` mislabel found on the second pass. The original
>    `policy` evidence is preserved unchanged as RC-5(a); the new material is
>    RC-5(b)/(c). Severity raised P3 → P2 accordingly.
>
> Nothing from the first pass was removed.

---

## 1. Core Logic & Implementation

### RC-1 [P2] `context_expand` double-subtracts the expansion reserve, so every handle it advertises in `next` is mathematically guaranteed to be refused at the same budget

**Spec.** SYSTEM_BEHAVIOR §31.1 (line 3183–3188):

> `context_expand` budgets against the **cumulative** pack: the tokens already
> consumed by the pack's selected items seed the budget, so a newly expanded item is
> admitted only if it fits within `limit_tokens` alongside everything already
> selected.

§31.4 (3267–3268) further lists "reserved expansion budget" as a distinct budget
dimension, and §31.2 names the request field `reserve_for_expansion`. The reserve
exists *so that expansion has headroom*; `context_fetch` withholding it is correct,
`context_expand` withholding it again is not.

**Code.** `backend/src/curator/context_service.py:195-220` (fetch side):

```python
def _apply_budget(items, *, limit_tokens):
    limit = max(0, limit_tokens)
    reserved = min(_DEFAULT_RESERVED_TOKENS, max(0, limit // 4))
    available = max(0, limit - reserved)
    ...
    for item in items:
        cost = _estimate_tokens(item.text)
        if used + cost <= available:
```

`backend/src/curator/context_service.py:464-498` (expand side):

```python
def _budget_payloads(items, *, limit_tokens, already_used=0):
    limit = max(0, limit_tokens)
    reserved = min(_DEFAULT_RESERVED_TOKENS, max(0, limit // 4))
    available = max(0, limit - reserved)      # <-- reserve withheld a SECOND time
    ...
    used = max(0, already_used)
    for item in items:
        cost = _payload_token_cost(item)
        if used + cost <= available:
```

`already_used` is seeded from the stored selection at `context_service.py:765`:

```python
already_used = sum(_payload_token_cost(item) for item in selected_candidates)
```

and `_payload_token_cost` (line 460-461) reads the payload's `token_cost`, which
`_item_payload` (line 454) set to exactly `_estimate_tokens(item.text)` — the same
number `_apply_budget` accumulated. So both sides use an *identical* cost function
and an *identical* `available` for a given `limit_tokens`.

**Proof that no `next` handle can ever be admitted at the same `limit_tokens`.**
Let `A = limit - reserved`. `context_fetch` omitted item *i* precisely because
`used_i + cost_i > A`, where `used_i` is the running total at that step. Because
`used` is monotonically non-decreasing, the final `used_final ≥ used_i`, hence
`used_final + cost_i > A`. `context_expand` evaluates exactly
`already_used(= used_final) + cost_i <= A`, which is therefore always false.
Every item in `next` is returned as `expansion_refused / budget_exhausted`.

**Concrete failure scenario (real surface defaults, not synthetic).**
`plugin_api/context.py:17` defaults `fetch_context(limit_tokens=8000)` and
`plugin_api/context.py:58` defaults `expand_context(limit_tokens=8000)`; the CLI
mirrors both at `commands/plugin.py:514,539`. With `limit_tokens=8000`,
`reserved = min(1000, 2000) = 1000`, `available = 7000`. Say `context_fetch` selects
7 items of 900 tokens (`used=6300`) and omits the 8th (900 tokens, `6300+900>7000`).
The plugin then calls `wiki plugin context-expand --limit-tokens 8000` with that
item's handle: `available=7000`, `already_used=6300`, `6300+900 = 7200 > 7000` →
refused. Yet `7200 ≤ 8000 = limit_tokens`, so §31.1's admission rule says it MUST be
admitted. The 1000-token expansion reserve is dead capital that nothing can spend,
and the progressive-expansion surface is inert on its own default path.

**Existing tests do not pin the correct behavior.**
`backend/tests/test_plan_f_context_service_contract.py:656-692`
(`test_context_expand_consumes_successful_handles_once`) fetches with
`limit_tokens=20` and then expands with `limit_tokens=400` — a 20× budget increase,
with the comment "A budget large enough for the cumulative pack so the first
expansion lands." That test only passes *because* it sidesteps the equal-budget
case. No test asserts that a handle offered by `next` is admissible at the budget
that produced it.

**Fix direction.** In `_budget_payloads`, do not re-withhold the reserve: enforce
`already_used + cost <= limit_tokens` (optionally still reporting
`reserved_tokens` for symmetry), or thread the fetch-time `reserved` value through
the stored context and add it back (`available = limit - reserved + reserved_fetch`).
Add a regression test: fetch at limit L producing a non-empty `next`, then expand at
the *same* L, and assert the first handle is admitted.

---

### RC-2 [P1] `context_expand` / `context_verify` never recompute the snapshot — the conflict check is a tautology against the pack's own stored id

> **Severity raised to P1 on the second pass.** The first pass rated this P2
> ("contract violation, silent degradation"). The sharper reading: this is not a
> weak or partial check — `_snapshot()` is *never invoked* on the expand/verify
> paths (`grep` for `_snapshot(` in `context_service.py` yields only lines 542 and
> 696, both inside `context_fetch`/`context_manifest`), so the guarantee has **no
> implementation whatsoever** on those operations. The result is user-visible —
> an agent answers from evidence whose source no longer exists, citing it as
> current — and there is **no client-side workaround**, because the only signal
> the contract offers the client is the `snapshot_conflict` response that can
> never be produced. That matches "P1 = user-visible breakage with no
> workaround". A red-teamer arguing for P2 has a defensible case (the served text
> was legitimately retrieved once, so this is stale-serving rather than
> fabrication); a red-teamer arguing P0 ("serving wrong knowledge") also has one.
> P1 is the deliberate middle.

**Spec.** SYSTEM_BEHAVIOR §31.3 (3225–3235):

> The service resolves one immutable snapshot per request. The snapshot closure
> includes source/corpus identity, DB epoch, search/index epoch, dependency or
> derived-state epoch, `curate.yml` policy hash, model/tokenizer/config identity,
> and creation time. … `context_expand` requires `pack_id`, expansion handles, a new
> budget, and `expected_snapshot_id`. **If any snapshot component changed, the
> service returns a typed conflict with `current_snapshot_id` and does not mix
> epochs silently.**

**Code.** `context_fetch` does this correctly — it recomputes and compares
(`context_service.py:542-544`):

```python
snapshot = _snapshot(self.paths, policy_hash=policy_hash, request=request)
if expected_snapshot_id and expected_snapshot_id != snapshot["snapshot_id"]:
    return _conflict_response(expected_snapshot_id, snapshot["snapshot_id"])
```

`context_expand` does not (`context_service.py:744-750`):

```python
trace, context = self._find_context_pack_by_pack_id(pack_id)
if trace is None or context is None:
    return {"ok": False, "error_type": "pack_not_found", "pack_id": pack_id}
snapshot = context["snapshot"]                      # <-- the STORED snapshot
current_snapshot_id = str(snapshot["snapshot_id"])  # <-- not a live recomputation
if expected_snapshot_id != current_snapshot_id:
    return _conflict_response(expected_snapshot_id, current_snapshot_id)
```

`context_verify` repeats the identical pattern at `context_service.py:869-872`, and
`context_feedback` reads the stored snapshot at `context_service.py:952-953`.

Because `current_snapshot_id` is read out of the persisted pack, it is by
construction the value the client received from `context_fetch`. The comparison can
only ever fail when the *client* fabricates or transposes an id — never when the
underlying epoch actually moved. `_snapshot` is never called on the expand path at
all (it appears only at lines 542 and 696).

**Concrete failure scenario.** Agent calls `context_fetch` → gets `PACK-x` /
`SNAP-abc` with 3 selected items and 5 budget-omitted handles. The user then deletes
a source and runs `wiki update`, which rewrites `sources` / `source_spans` and
regenerates L2–L4. The agent calls `context_expand(pack_id="PACK-x",
expected_snapshot_id="SNAP-abc", handles=[...])`. The stored snapshot id is still
`SNAP-abc`, so the equality holds, no conflict is returned, and the service serves
the expanded item straight out of `context["omitted_items"]` — text, `record_hash`,
`source_span_ids`, and locator all captured before the deletion. The agent receives
evidence for a record that no longer exists, cited as current. That is exactly the
"mix epochs silently" outcome §31.3 forbids.

**Existing tests do not pin the correct behavior.**
`test_plan_f_context_service_contract.py:737` passes a literal
`expected_snapshot_id="SNAP-stale"` — the client-mismatch case only. There is no
test that mutates the DB between `context_fetch` and `context_expand` and asserts a
`snapshot_conflict`.

**Fix direction.** On expand/verify (and feedback), recompute `_snapshot(...)` from
the live DB using the policy hash + request fields already persisted in the stored
snapshot closure, compare the *recomputed* id against both `expected_snapshot_id`
and the stored id, and return `_conflict_response(expected, recomputed)` when they
diverge. Persist enough of the request closure in `context["snapshot"]` for the
recomputation to be exact (see RC-3).

---

### RC-3 [P2] The snapshot closure omits the search/index epoch, derived-state epoch, model identity, and `created_at` mandated by §31.3/§31.4

**Spec.** §31.3 (3226–3230) enumerates the closure: "source/corpus identity, DB
epoch, search/index epoch, dependency or derived-state epoch, `curate.yml` policy
hash, model/tokenizer/config identity, and creation time." §31.4 (3246) shows the
pack's snapshot object as `{"snapshot_id": "SNAP-...", "created_at": "..."}`.

**Code.** `context_service.py:136-178`:

```python
def _source_epoch(paths):
    ... "SELECT id, content_hash FROM sources ORDER BY id"
    ... "SELECT id, content_hash FROM source_spans ORDER BY id"

def _snapshot(paths, *, policy_hash, request):
    closure = {
        "contract_version": "1",
        "schema_version": db.SCHEMA_VERSION,
        "workspace_path": str(paths.root.resolve()),
        "source_epoch": _source_epoch(paths),
        "policy_hash": policy_hash,
        "request": {...},
        "tokenizer": "conservative",
    }
    digest = hashlib.sha256(json.dumps(closure, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "snapshot_id": f"SNAP-{digest[:12]}",
        "source_epoch_hash": ...,
        "db_schema_version": db.SCHEMA_VERSION,
        "policy_hash": policy_hash,
        "tokenizer": "conservative",
    }
```

Present: source/corpus identity (`sources` + `source_spans`), DB epoch
(`SCHEMA_VERSION`), policy hash. **Absent:** any search/index epoch
(`search_documents` / `search_chunks` / embedding provider+model+dimension), any
derived-state epoch (`knowledge_units`, `graph_relations`, `community_reports`,
`synthesis_nodes`), real model/config identity (`"tokenizer": "conservative"` is a
hard-coded literal, not the active embedder/reranker/LLM fingerprint), and
`created_at` (the returned dict has no such key; the only `created_at` in the module
is `context_service.py:1112`, read off the trace row, not the snapshot).

**Concrete failure scenario.** `wiki reindex --embed` rebuilds `search_documents`
and re-embeds the corpus with a different provider/model; or a `wiki update` run
regenerates L3 concepts and L4 synthesis without adding or removing a source row.
Neither touches `sources.content_hash` or `source_spans.content_hash`, so the
closure digest is byte-identical and `snapshot_id` is unchanged. A client that
correctly passes `expected_snapshot_id` to `context_fetch` gets no conflict, and the
new pack silently mixes the old ranking regime with the new index. Fixing RC-2
alone would not catch this, because the recomputed id would also be unchanged —
RC-2 and RC-3 must be fixed together for §31.3 to hold.

Separately, `pack["snapshot"]["created_at"]` promised by §31.4 is a `KeyError` for
every caller today.

**Fix direction.** Extend `_snapshot`'s closure with (a) a search/index epoch
(count + hash over `search_documents(id, content_hash|updated_at)` and the active
embedding `provider::model::dim`), (b) a derived-state epoch over the L2–L4 record
tables, (c) the real embedder/reranker/tokenizer fingerprints instead of the literal
`"conservative"`, and (d) emit `created_at` on the returned snapshot dict (excluded
from the digest so the id stays deterministic). Update SEARCH_ENGINE_SCHEMA/
SYSTEM_BEHAVIOR if any component is deliberately dropped.

---

### RC-4 [P2] A runtime LLM query-expander failure is swallowed twice and the trace then *claims* the expander ran

**Spec.** SEARCH_ENGINE_SCHEMA §8 (320–322):

> Warnings should use stable machine-readable prefixes such as
> `vector_unavailable`, `vector_failed`, `query_expander_unavailable`, and
> `reranker_failed`.

SYSTEM_BEHAVIOR §32 (3403–3406): "False success is forbidden. … Optional
classification or suggestion failures may preserve deterministic fallback output,
but the suppressed cause remains observable in logs."

**Code — swallow #1**, `retrieval/query_expander.py:140-159`:

```python
def __call__(self, raw: str) -> dict:
    ...
    except Exception:
        return {}
    try:
        completion = cast(dict[str, Any], result)
        text = str(completion["choices"][0]["text"])
    except Exception:
        return {}
```

**Swallow #2**, `retrieval/expansion.py:97-101`:

```python
if expander is not None:
    try:
        extra = expander(raw) or {}
    except Exception:
        extra = {}
```

Neither logs. Neither returns a failure signal. **The engine then records a
positive claim**, `retrieval/engine.py:270-283` and `364-377`:

```python
use_expander = self.expander is not None and (
    not expansion_recovery_only or recovery_needed
)
if self.config.get("query_expansion", True) and self.expander is None and want_hyde:
    warnings.append("query_expander_unavailable: using deterministic expansion only")
...
"expansion": {
    ...
    "used": use_expander,          # True even when the expander raised
    "hyde_used": bool(expanded.hyde_text),
},
```

`use_expander` is computed from *configuration* (`self.expander is not None`), never
from the outcome. The only `query_expander_unavailable` emission is gated on
`self.expander is None` — i.e. it fires when the expander was never built, and
never when a built expander fails at query time.

**Concrete failure scenario.** `search.query_expander` is configured to a local
GGUF model whose file was moved, or `llama_cpp` OOMs on the first
`create_completion`. Recovery-only expansion triggers (`lex_hit_count=2 < 5`), so
`use_expander=True` and `want_hyde=True`. `LlamaCppExpander.__call__` raises inside
llama.cpp → `{}` → no `lex_exp`, no `vec_exp*`, no `vec_hyde` list is fused. The
user gets a thin, unrecovered result set. The persisted
`query_traces.retrieval_trace_json` says `expansion.used = true`,
`expansion.recovery_needed = true`, `hyde_used = false`, `warnings: []` — i.e. the
dashboard reports that recovery expansion ran successfully and simply found nothing.
No log line records the cause anywhere.

**Existing tests do not pin the correct behavior.** `query_expander_unavailable`
appears exactly once in the whole repo — at `engine.py:274` — with no test
referencing it (`grep -rn "query_expander_unavailable" backend/tests/` is empty).

**Fix direction.** Have the expander callable surface failure (return a typed
result or let `expansion.expand` catch-and-record), set
`expansion.used` from the *actual* outcome, append
`query_expander_unavailable: <ExcType>: <msg>` to `warnings`, and add
`logger.warning(..., exc_info=True)` at both swallow sites per §32.

---

### RC-5 [P2] Contract fields promised by §30.2 / §31.4 / §31.5 are never written, and `layer` is populated with the item *kind* instead of a DAG layer

> **Broadened and raised P3 → P2 on the second pass.** The first pass reported only
> sub-finding (a) (the missing `policy` block) at P3. Re-auditing `_item_payload`
> against §31.5 field-by-field surfaced two more instances of the same defect
> class — required contract fields that the code simply never emits, plus one
> field that is emitted with structurally wrong content. Together these are a
> contract violation with real consumer impact, not doc drift. All original (a)
> evidence is preserved verbatim below.

#### RC-5(a) — the `policy` block mandated by §30.2 is never written into any trace

**Spec.** SYSTEM_BEHAVIOR §30.2 (3113–3134) defines the retrieval result carried on
`EvidencePack` and persisted in the QTR trace, and it is described as "the only
authoritative record of the retrieval execution for Plan F consumption":

```json
{
  "contract_version": "1",
  "retrieval_execution_id": "RTR-...",
  "route": {"selected": "local", "reason": "..."},
  "policy": {"source_include": [], "source_exclude": []},
  "selection": {"candidate_count": 12, "selected_count": 8, "omitted_counts": {}},
  "warnings": []
}
```

**Code.** `context_service.py:101-121` builds that exact object and writes every
field *except* `policy`:

```python
def _build_retrieval_trace(pack, route, reason, *, selected_items, omitted_counts):
    base = pack.retrieval_trace.copy() if pack.retrieval_trace else {}
    base.update({
        "contract_version": "1",
        "retrieval_execution_id": pack.retrieval_execution_id,
        "route": {"selected": route, "reason": reason},
        "selection": {
            "candidate_count": len(pack.items) + sum(pack.omitted_counts.values()),
            "selected_count": len(selected_items),
            "omitted_counts": omitted_counts,
        },
        "warnings": pack.warnings,
    })
    return base
```

`grep -rn "source_exclude\|source_include" backend/src/curator/context_service.py
backend/src/curator/retrieval/*.py` returns **zero** hits — the resolved
`CurationPolicy` reaches `build_evidence` (correctly, per §28.1) but its glob scope
is never recorded on the trace it produced. `pack.retrieval_trace` is the engine's
SEARCH_ENGINE §8 search trace (`engine.py:364-384`), which also has no `policy` key,
so `base` cannot supply it.

**Concrete failure scenario.** A workspace `curate.yml` sets
`source_exclude: ["06_Archives/**"]`. A user asks why an archived paper never shows
up and inspects `query_traces.retrieval_trace_json` (or the dashboard that renders
it). `selection.omitted_counts` shows `{"policy_excluded": 4}` — four items were
dropped — but *which* policy did the dropping is unrecoverable from the trace,
because `curate.yml` may have been edited since. The §30.2 promise that the trace
explains the execution "without re-running the query" is broken for the one
dimension that silently removes evidence.

**Existing tests do not pin the correct behavior.** No test in
`backend/tests/test_plan_f_context_service_contract.py` asserts a `"policy"` key on
the trace.

**Fix direction.** One line in `_build_retrieval_trace`: accept the resolved
`policy` (already in scope at `context_service.py:556`) and add
`"policy": {"source_include": list(policy.source_include), "source_exclude":
list(policy.source_exclude)}`. Add a contract assertion in the Plan-F test file.

Second-pass confirmation of (a): `CurationPolicy` really does carry the two glob
tuples (`curate_yml.py:529-530`, `source_include: tuple[str, ...]` /
`source_exclude: tuple[str, ...]`), and
`grep -rn "source_include\|source_exclude" backend/src/curator/context_service.py
backend/src/curator/retrieval/*.py` still returns **zero** hits — the fields exist,
reach `build_evidence`, and are never recorded. `grep -n '"policy"'` across
`context_service.py`, `retrieval/*.py`, and `db/*.py` is likewise empty, so the key
is absent from the pack response (`context_service.py:651-691`) as well as the
trace, breaking §31.4's `"policy": {"applied_filters": [], "excluded": []}` too.

#### RC-5(b) — `_item_payload` omits four §31.5-required evidence-item fields

**Spec.** SYSTEM_BEHAVIOR §31.5 (3283–3293) — each selected item carries:

> `item_id`, stable `record_id`, `record_hash`, `kind`, and DAG `layer`; compact
> `summary` or `claim` distinct from raw source text; authority, truth/support, and
> freshness state; **ranking contributions and route/expansion reason**; structured
> locator, locator status, and minimal supporting `source_span_ids`; **immediate
> dependency ids**; **token cost and detail level**; **contradiction/uncertainty
> state**; `expansion_handle` and `verification_handle`.

**Code.** `context_service.py:433-457` — the complete emitted key set:

```python
return {
    "item_id": item.id,
    "record_id": item.id,
    "record_hash": hashlib.sha256(f"{item.kind}:{item.id}:{item.text}".encode("utf-8")).hexdigest(),
    "kind": item.kind,
    "layer": item.kind,
    "summary": item.title,
    "detail": item.text,
    "title": item.title,
    "text": item.text,
    "score": item.score,
    "community_report_id": item.community_report_id,
    "synthesis_node_id": item.synthesis_node_id,
    "memory_path_id": item.memory_path_id,
    "authority_state": "derived",
    "truth_state": truth_state,
    "freshness_state": freshness_state,
    "source_span_ids": item.source_span_ids,
    "locator": locator,
    "token_cost": _estimate_tokens(item.text),
    "expansion_handle": _expansion_handle(item.id),
    "verification_handle": _verification_handle(item.id),
}
```

Missing outright, with no equivalent under another name:

1. **ranking contributions / route-expansion reason** — only a bare scalar `score`
   is emitted. The per-list RRF contributions *are* computed
   (`fusion.rrf_fuse` → `FusedHit.contributions`, `fusion.py:59-61`) and *are*
   carried to `EngineHit.contributions` (`engine.py:355`), then thrown away when
   `evidence._search_hits` constructs the `EvidenceItem` (`evidence.py:219-224`
   copies only `id/kind/title/text/score/source_span_ids`). The data exists and is
   discarded one layer before the pack.
2. **immediate dependency ids** — no `dag_edges` lookup anywhere in
   `context_service.py`.
3. **detail level** — §31.2 (3216) defines four request detail levels
   (`manifest`/`index`/`excerpt`/`source`) but no item reports which one it was
   rendered at.
4. **contradiction/uncertainty state** — absent per item, and `coverage` in the
   response is built as only `{"sufficiency": …, "omitted_counts": …}`
   (`context_service.py:665-668`), so §31.4's `coverage.contradictions_present`
   and `coverage.omission_categories` are absent as well.

**Concrete failure scenario.** A `purpose="verify"` agent (§31.2 allows exactly
this purpose) fetches a pack to check a contested claim. Nothing in the pack tells
it that two of its items contradict each other — `contradictions` are only
reachable through a *separate* `context_verify` round trip per item
(`context_service.py:859-891` region, whose response carries `contradictions`, as
pinned by `test_plan_f_context_service_contract.py:885`). With a 12-item pack that
is 12 extra service calls to recover a field §31.4 says belongs on the pack, and an
agent that trusts the contract simply never checks. Likewise a client that wants to
show "why was this ranked first" — the §31.5 ranking-contribution field — gets a
single opaque float whose scale silently changes between reranked and
`no_rerank` runs (`engine.py:186` blended `0..1` vs `engine.py:333` raw RRF
`~0.02`), with no contributions to explain it.

**Existing tests do not pin the missing fields.**
`test_plan_f_context_service_contract.py:39-56` asserts a *subset*
(`required <= set(item)`) against a **static fixture file**
(`context_fetch_pack.json`, loaded at line 20-21), not against live service output.
Its `required` set omits all four fields above, so the fixture and the code can both
drift from §31.5 without failing.

#### RC-5(c) — `layer` is a verbatim copy of `kind`, not a DAG layer

**Code.** `context_service.py:439-440`:

```python
"kind": item.kind,
"layer": item.kind,
```

`item.kind` takes exactly these values, assigned in `evidence.py`: `"entity"`
(:251), `"source_span"` (:276), `"community_report"` (:319), `"synthesis"` (:342),
`"memory_path"` (:423), `"search_hit"` (:221). None of these is a DAG layer under
the locked system invariants — the layers are `01_Contexts` / `02_Atoms` /
`03_Concepts` / `04_Synthesis` with prefixes `CTX-`/`ATM-`/`CON-`/`SYN-`. §31.5
names the field "DAG `layer`" as a field distinct from `kind`; here it is a
duplicate.

**Concrete failure scenario.** An external MCP agent implementing §31.5 filters its
pack to `layer in {"03_Concepts", "04_Synthesis"}` to build a high-altitude answer
and drops every item, because no item's `layer` is ever a layer name. It cannot
tell an L1 span from an L4 synthesis without reverse-engineering `kind`, and
`search_hit` — which can hydrate *any* record type (`engine._hydrate` returns the
document's own `record_type`, `engine.py:203`) — is unresolvable even then, because
`EvidenceItem` does not carry the hydrated `record_type` forward.

**Fix direction (b + c).** Map `kind` → DAG layer explicitly
(`source_span`→`01_Contexts`, `entity`→`02_Atoms`, `community_report`→`03_Concepts`,
`synthesis`→`04_Synthesis`, `search_hit`→the hydrated record's own type, which
means threading `EngineHit.record_type` into `EvidenceItem`) and keep `kind` for the
retrieval-shape distinction. Add `detail_level` (from `request.detail`),
`dependency_ids` (from `dag_edges`), `ranking` (thread the already-computed
`EngineHit.contributions` through `evidence._search_hits`), `contradiction_state`,
and `coverage.contradictions_present` / `coverage.omission_categories`. Bump the
pack `contract_version` — `layer`'s value changes shape, so a consumer that learned
the current `kind`-like values will break. Replace the fixture-only assertion in
`test_context_fetch_fixture_pins_pack_contract` with (or add alongside it) an
assertion over **live** `context_fetch` output so the fixture cannot drift.

---

## 2. Pros & Cons

### What I judged clean (checked and found conformant)

- **§28.1 strict all-spans scope rule.** `evidence.py:56-110` — `_item_in_scope`
  keeps an item only when *every* backing span is in scope, `_apply_policy_scope`
  never mutates `source_span_ids`, and `omitted_counts["policy_excluded"]`
  accumulates the drop count. `_apply_policy_scope` is invoked on all four route
  branches (`evidence.py:391, 411, 438, 447`). Matches the spec sentence-for-sentence.
- **§31.4 provenance dedupe/ordering.** Both `_selected_refs`
  (`context_service.py:223-251`) and `_selected_refs_from_payloads`
  (`context_service.py:254-292`) dedupe by first occurrence while iterating selected
  items and never sort. No lexicographic re-sort anywhere on the pack path. (The
  engine *does* `sorted(...)` its span ids at `engine.py:395`, but that is the
  diagnostic search QTR, not the §31.4 pack, so it is out of contract scope.)
- **§31.5 handle consumption.** `context_expand` removes admitted handles from
  `omitted_items` (`context_service.py:820-824`) and appends the `expansion` action
  only when something was admitted (`if selected:` at line 808), so a repeated
  handle returns no duplicate item and no second action — pinned by
  `test_context_expand_consumes_successful_handles_once`.
- **§31.5 refusals not requeued.** `expansion_refused` carries
  `reason="budget_exhausted"` + `retry="increase_limit_tokens_or_refetch"` and
  `next` is `[]` on both expand return paths (`context_service.py:790, 855`).
- **§31.8 admission gate.** `_admit_route` (`context_service.py:42-57`) runs before
  `build_evidence` (line 548 precedes 556), `_SAFE_ROUTES` are never disabled, and
  `route_admission` with all five keys is written to both the response (line 662)
  and the trace's `context_service` payload (line 619). `explore` is in
  `_ADMITTED_ROUTES` and `orchestrator.run` grounds it through the same
  `context_fetch` (`orchestrator.py:58, 76-79`) — no divergent second pipeline.
- **§31.5 `orphaned_support`.** `_item_payload` (`context_service.py:419-432`)
  downgrades to `truth_state="orphaned_support"` + `freshness_state="stale"` when
  the locator is missing/`unavailable`, never labelling it `source_supported`;
  pinned by the test at `test_plan_f_context_service_contract.py:610-619`.
- **§31.6 feedback.** Locked type set at `context_service.py:60-73` matches the nine
  spec types exactly.
- **SEARCH_ENGINE §8 provider boundaries.** `_vector_list`
  (`engine.py:116-142`) routes every embedding failure — exception, wrong count,
  empty/non-finite vector via `_validate_embedding_output`, dimension mismatch via
  `VectorCompatibilityError` — into a single `vector_failed: …` warning, and
  `engine.py:289-309` skips all later vector-expansion calls for that query once
  `vector_failed` is set. Reranker invalid output keeps RRF order and records
  `reranker_failed` (`engine.py:180-182, 328-331`).
- **§30.4 no orphan QTR.** `context_fetch` always preallocates and persists the root
  `QTR-*` (`context_service.py:581, 623`) and attaches the `RTR-*` as the order-1
  `retrieval` action (line 585-590).

### Limitations of this audit / what I could NOT verify

- **Read-only, no execution.** Per the arena ground rules I ran no `wiki` command
  and no `pytest`. The RC-1 proof is analytic (identical cost function, identical
  `available`, monotone `used`) rather than executed; a red-teamer should confirm it
  with a five-line test before it enters the Master Plan.
- **RC-3 severity depends on real churn rates.** I did not measure how often
  `search_documents` / L2–L4 tables move without `sources` / `source_spans` moving.
  If in practice every reindex is preceded by a source change, the practical blast
  radius is smaller than the contract gap suggests.
- **I did not audit** `search.py`, `query.py`, `materializer.py`, `lexical.py`,
  `vector.py`, `embedding.py`, or `router.py` beyond the call sites named above —
  token discipline forced depth over breadth. The `_CANDIDATE_CAP`/`fuse_cap`
  interaction and the `min_score` "keep at least one hit" fallback
  (`engine.py:359-361`) look suspicious but I did not read enough of the spec to
  make a claim.
- **Two near-misses I deliberately dropped**, both weaker than the five above:
  (a) `engine.py:381` publishes the module-level mutable `fusion.DEFAULT_WEIGHTS`
  by reference into the trace, and its keys (`vec_exp`) do not match the list names
  actually fused (`vec_exp1`, `vec_exp2`), so a consumer joining `lists` against
  `weights` cannot resolve them — but `fused[].contributions` carries the weight
  inline, so §8 is technically satisfied; (b) `engine.py:311` sets
  `fallback_mode="lex"` for an explicitly requested `mode="lex"` search, labelling a
  full-quality lexical request as degraded — arguable either way from §8's wording.
- **Fix sequencing note for the synthesizer.** RC-2 and RC-3 are one repair, not
  two: recomputing the snapshot (RC-2) is useless while the closure is blind to the
  index and derived-state epochs (RC-3). RC-1 is independently shippable and is the
  only finding here that breaks a user-facing flow outright.

### Second-pass additions (same persona, independent re-audit)

**Additionally judged clean — checked on the second pass, no finding raised:**

- **§31.4 CJK-safe token estimation.** `_estimate_tokens`
  (`context_service.py:181-184`) returns
  `max(1, (len+3)//4, (utf8_bytes+2)//3)`. Three-byte Hangul/CJK therefore yields
  ≈1 token per character rather than the English-only `/4` divisor §31.4 (3270-3272)
  explicitly forbids. Conformant.
- **§31.1 cumulative-budget *seeding* is correct** even though the reserve handling
  is not (RC-1). `already_used` (`context_service.py:765`) is exactly the fetch-time
  `used_final`, and both sides call the identical cost function
  (`_estimate_tokens` at `:454` vs `_payload_token_cost` at `:460-461`). There is no
  *drift* between `context_fetch` and `context_expand` accounting — RC-1 is a
  systematic offset, not a divergence, which matters for how it is fixed.
- **§28.1 candidate-mass conservation.** `_build_retrieval_trace`
  (`context_service.py:115`) computes
  `candidate_count = len(pack.items) + sum(pack.omitted_counts.values())`. Budget
  omissions are *not* double-counted, because budget-trimmed items are still inside
  `pack.items`, and `"budget"` is added only to the local `omitted_counts`
  (`:567-570`), never to `pack.omitted_counts`. Arithmetic checks out on all four
  routes.
- **§28.2 bounded global route.** `_MAX_GLOBAL_REPORTS = 10` /
  `_MAX_GLOBAL_SYNTHESIS = 6` (`evidence.py:29-30`) are applied at
  `evidence.py:396-398`, ranking is lexical overlap over `title + summary` with a
  `rank`-based tiebreak (`_report_score`, `evidence.py:287-294`), and the remainder
  is recorded as `omitted_counts["global_reports"]` (`evidence.py:407-408`).
  Matches §28.2 sentence-for-sentence.
- **§31.8 explore is a pack consumer, not a second pipeline.** `orchestrator.run`
  calls `ContextService.context_fetch` unconditionally (`orchestrator.py:58`) and
  only *then* branches on the served route (`:76-79`); `_run_explore_from_context`
  (`:195-246`) consumes `context_pack["items"]` and never re-retrieves. Explore
  synthesis failure preserves provenance (`:222-225` returns without clearing the
  arrays), matching the comment at `:136-142` for the answer path. Conformant.

**Additional things I could NOT verify on the second pass:**

- **RC-1/RC-2 executed reproduction.** Ground rule 2 forbids mutating `wiki`
  commands and testbed writes, and ground rule 1 forbids writing tests. Both
  findings remain analytic (RC-1) or structural (RC-2). A red-teamer with write
  access should confirm RC-1 with a five-line test (fetch at limit L with a
  non-empty `next`, expand at the same L, assert the first handle is admitted) and
  RC-2 by inserting a `sources` row between fetch and expand and asserting
  `error_type == "snapshot_conflict"`.
- **Whether any live MCP/plugin caller round-trips `expected_snapshot_id` across a
  corpus mutation.** `mcp/server.py` and the plugin context client belong to other
  inspector domains; RC-2's *blast radius* is therefore unquantified even though the
  contract break itself is unconditional.
- **`_apply_policy_scope` memory-path id leak — investigated and deliberately NOT
  reported.** `evidence.py:127-128` rebuilds `pack.memory_path_ids` only under
  `if mpaths:`, whereas `community_report_ids` / `synthesis_node_ids` are rebuilt
  unconditionally (`:125-126`). So an explore pack whose memory-path items are *all*
  policy-excluded retains the excluded ids, contradicting the function's own
  docstring ("rebuilds the per-kind id lists from the survivors so no excluded
  span/report/synthesis lingers"). It is not reachable today:
  `grep -rn "build_evidence" backend/src/` shows exactly one caller
  (`context_service.py:556`), and `context_fetch` recomputes every provenance array
  from the surviving *items* via `_selected_refs` (`:561, 634, 685-688`). Worth a
  one-line hardening if the batch touches that function; not a defect on its own.
- **Partial-resolution `truth_state` for multi-span items.** `_item_locator`
  (`context_service.py:389-411`) returns the *first* resolvable span locator, so a
  community report backed by 5 spans of which 4 are unresolvable still reports
  `truth_state="source_supported"` — arguably against §31.5's "**all** minimal
  support ids and locators must resolve or the item is either excluded or returned
  with an explicit degraded/provisional state". Left out because it sits directly on
  the CAND-04 locator surface the briefing reserved, and the honest fix belongs in
  the same change as CAND-04.
- **`engine.retrieval_trace["fused"]` ordering.** `engine.py:379` emits
  `fused[:limit]` in **pre-rerank RRF order** while the returned `hits` are in
  post-rerank blended order (`engine.py:336-357`), so the trace's `fused` list can
  disagree with the served ranking in both order and membership. SEARCH_ENGINE §8
  (313-315) only mandates that `fused[].contributions` show list/rank/weight/
  contribution — it fixes neither ordering nor membership — so I could not call this
  a violation without stretching the text. Flagged for the synthesizer, not reported.
- **`fallback_mode` collapse.** `engine.py:327` does
  `fallback_mode = fallback_mode or "no_rerank"`, so a query that degrades on both
  vector *and* rerank reports only `"lex"`. §8 (316-319) describes `fallback_mode`
  as a single scalar and both causes still surface in `warnings`
  (`engine.py:314-316, 329-331`), so this is defensible as written. Not reported.
  This is the same judgement the first pass reached on the neighbouring
  `mode="lex"` labelling question.

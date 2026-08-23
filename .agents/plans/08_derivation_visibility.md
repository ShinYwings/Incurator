# v0.67.0 Master Implementation Plan — A7: make the empty derivation visible

## 1. Objective

Record, per query, **whether a search-query derivation ran, whether it returned
nothing, and what intent it stated** — and surface it where a human will see it.

A7 exists because this was measured wrong twice. Two separate single-run
observations of the same question produced an empty derivation, and a design was
built on the premise that empty was a deliberate, stable signal. Running the same
question eight times gave **0/8 empty** and a **6-in-8 route flip** instead — an
entirely different bug. One sample was mistaken for a property, twice, because
nothing stored enough to check.

## 2. Explicit Non-Goals

- **Not** fixing the derivation gap itself. Three of four surfaces never derive;
  that is **A8**, and it is deliberately next rather than now.
- **Not** changing `choose_route`'s logic. Routing behaviour is untouched.
- **Not** storing the question text. `question_hash` already groups repeated runs
  of the same question, which is all the measurement needs.

## 3. Strict Quality Conditions & Release Gates

- `pytest`, `ruff`, `mypy` green; plugin vitest green; CI green before merge.
- A test that **fails if the recorded status is hardcoded** rather than read from
  the request — the mutation that would make this feature decorative.
- The new field must be readable back through the **production** path
  (`wiki inspect answer`), not through a reimplementation in the test.

## 4. Locked Design Decisions

### 4.1 The block goes in `retrieval_trace.context_service.derivation`

`route_admission` is the precedent: a structured sub-block inside
`context_service` recording one routing decision. `derivation` is its sibling.
Both `insert_query_trace` re-entry points (`context_service.py:1117`,
`orchestrator.py:175`) copy the `context_service` dict forward wholesale, so the
block survives the action-append rewrites without touching either.

```python
"derivation": {
    "status": request.english_query_status,          # "unset" | "derived"
    "search_query_empty": not request.english_query.strip(),
    "routing_intent": request.intent,                # "" | lookup|synthesis|discovery
}
```

### 4.2 It is `routing_intent`, NOT `intent` — a name collision that is already loaded

`retrieval_trace["intent"]` **already exists** at the top level and means
something else entirely: `ExpandedQuery.intent` ∈
`{definition, comparison, procedure, default}` (`retrieval/expansion.py:43-67`),
a keyword-cue detector that steers **query expansion**. The routing intent is
`{lookup, synthesis, discovery}` and comes from the LLM.

Two different vocabularies, two different mechanisms, one word. Writing the
routing intent as `intent` would put both in one JSON document and leave the
next reader to work out which is which from context. `routing_intent`, plus a
comment at the write site naming the other one, is the whole fix — this is the
A5 lesson applied before the resemblance exists rather than after.

### 4.3 Additive only — the fixtures allow it

`docs/specs/system_behavior/context_service_fixtures/` is asserted with **subset**
checks (`required <= set(item)`, `test_plan_f_context_service_contract.py`), not
exact equality, so a new key breaks nothing. `contract_version` stays `"1"`:
nothing in the codebase switches on it, and an additive key does not invalidate
a reader of the old shape.

### 4.4 Stored is not enough — it must print

Phase A is *make failure visible*. `_format_query_trace` already forwards the
whole `retrievalTrace`, so `wiki inspect answer --json` gets this for free. But
the human summary (`commands/common.py:73-78`) prints only `route=` — not even
`routeReason`. A datum that requires `--json | jq` to see is not visible.

`_print_audit_summary` gains **one** line, printed only when the block exists.

### 4.5 `status: "unset"` on CLI/MCP is the honest answer, and it is the point

Three surfaces never derive (A8). This trace will record `unset` for all of them.
That is not a gap in A7 — it is A7 **working**: A8's defect becomes visible in
stored data instead of being something two releases missed.

## 5. Scope Exclusions & Stop Conditions

- No schema migration. `retrieval_trace_json` is a JSON column; no DDL changes.
- No change to the engine path (`engine.py:444`), which has no `QueryRequest` at
  all and records `route_reason="hybrid_engine"`.
- Stop and escalate if recording this requires changing when `choose_route` runs.

## 6. Evidence Ledger

- Rollback anchor: `2a5d1e5` (v0.66.0 merge).
- Pre-state: `retrieval_trace` records `mode`, `intent` (expansion), `is_cjk`,
  `expansion`, `lists`, `fused`, `fallback_mode`, `weights`, `fuse_cap`,
  `latency_ms`; `context_service` records `contract_version`, `pack_id`,
  `snapshot`, `actions`, `budget`, `route_admission`, `selected_items`,
  `omitted_items`. **Nothing records whether a derivation ran.**
- Post-validation: run one question through the production path twice and read
  both traces back with `wiki inspect answer`.

## 7. Execution Phases

- **P1** — failing test: a trace written through `ContextService` carries
  `derivation.status`/`search_query_empty`/`routing_intent` matching the request.
- **P2** — write the block at the `context_service.py` insert site. Green.
- **P3** — failing test: `_print_audit_summary` shows the derivation line.
- **P4** — print it. Green.
- **P5** — mutation check: hardcode `status="derived"` and confirm P1 fails.
- **P6** — docs: `SYSTEM_BEHAVIOR.md` §17 (what is recorded), `USER_GUIDE.md` +
  `_KR.md` (`wiki inspect answer` output), version bump, CHANGELOG.

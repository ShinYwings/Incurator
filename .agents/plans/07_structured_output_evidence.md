# Evidence Ledger — v0.60.0 structured output

Date: 2026-08-19 | Plan: `.agents/plans/07_structured_output.md`

## Rollback anchor

- `master` at `ce3e655` (v0.59.0 merged as `372c23d`).
- Branch: `feature/v0.60.0-structured-output`.
- No schema change, no migration. A revert is a code revert.
- **Another session holds `fix/db-connect-commit-and-chunk-floor`**, touching
  `db/schema.py` and `pipeline/knowledge_units.py` chunking. Do not edit those.

## The incident this fixes

Jobs 76 (Hartley, batch 37/277, 29 minutes) and 66 (Nicholson, 9/15) — the two
largest sources — failed with:

```
permission check failed for command "python3 -c '\nimport json\n\ndata = {...}'"
python3 -c '\nimport json, jsonschema\n\nallowed_spans = {...}'
```

Asked for JSON, the agentic CLI wrote a Python program to build (76) and to
validate (66) its own answer. 34 of 36 jobs never took that route — the choice
is non-deterministic.

## P0 — envelope reality, all measured on the real CLI

### 1. `--json-schema` accepts a STRING, not only a path

```
$ agy -p "<prompt>" --json-schema "$(cat flat_schema.json)" --output-format json
status=SUCCESS turns=1 units=1
```

**D6 resolves to the string form.** No temp file per call, so F4's "277 temp
files" concern disappears entirely rather than being managed.

`--json-schema` requires `--output-format json`; with `text` it errors out
before running.

### 2. Envelope shape

Success:

```
conversation_id, duration_seconds, json_schema, num_turns, response,
status, structured_output, usage
```

Error (forced with `--model definitely-not-a-real-model-xyz`):

```
conversation_id, duration_seconds, error, num_turns, response, status, usage
```

`status` is `"SUCCESS"` / `"ERROR"`. On error there is **no** `structured_output`
and **no** `json_schema` key.

### 3. The error path keeps its exit code but MOVES THE REASON — this changes P4

```
$ agy ... --output-format json   (bad model)
exit=1
stdout: {"status":"ERROR", "error":"invalid model selection (--model ...)", ...}
stderr: (empty)
```

The exit code is preserved, so `_run`'s `if result.returncode != 0` still fires.
But **stderr is empty**, and today the client builds its message from stderr:

```python
raise AntigravityCliError(f"Antigravity CLI exited {result.returncode}: {stderr}")
```

Under the envelope that raises `"Antigravity CLI exited 1: "` — the reason
silently lost. **P4 must read the envelope's `error` field for the message.**

### 4. Capacity detection is NOT broken, but its margin shrinks

`_raise_capacity_error` is reached via `_is_capacity_error(stderr) or
_is_capacity_error(log_text)` — stdout is not consulted, so the envelope does
not break it. But with stderr now empty, **the log file becomes the only
surviving signal**. P4 should also feed the envelope's `error` field to
`_is_capacity_error` rather than relying on the log alone.

### 5. Schema shape decides everything (the finding that reversed the design)

Same prompt, same CLI, schema is the only variable:

| schema | status | num_turns | units in `structured_output` |
|---|---|---|---|
| real (`$defs` + `$ref`) | SUCCESS | 2 | **0** |
| flattened (no `$ref`) | SUCCESS | **1** | **2** |

The real schema does not error — it succeeds and returns nothing, leaving the
answer in `response` as a fenced block under invented field names
(`knowledge_unit`, `source_span_id`). Shipping without flattening would have
ingested every book to nothing while reporting SUCCESS.

Round-trip on the flattened path:

```
KnowledgeUnitExtractOutput.model_validate(structured_output) -> 2 units
fields: canonical_name, confidence, formula_centrality, source_span_ids,
        statement, truth_status, unit_type
```

The contract's own model validates the CLI output unmodified.

### 6. Unplanned finding: token accounting is currently a lie for this backend

`AntigravityCliClient.get_and_reset_token_usage()` returns a hardcoded
`(0, 0)`, so every agy job writes `input_tokens=0, output_tokens=0,
estimated_cost_usd=0` into `ingest_jobs`. The envelope carries the real numbers:

```json
"usage": {"input_tokens": 14158, "output_tokens": 830,
          "thinking_tokens": 715, "cache_read_tokens": 0, "total_tokens": 14988}
```

**Not in scope by default.** It is three lines once the envelope is parsed, and
the columns exist and are currently reporting zeros as if they were measured —
but it is a separate capability from the one this plan fixes. Flagged for an
explicit decision rather than folded in silently.

## Gate results

| gate | result |
|---|---|
| G1 real-schema round trip (live) | pending |
| G2 flattener | pending |
| G3 empty-structure fallback | pending |
| G4 `num_turns` warning | pending |
| G5 envelope success/error/capacity | **P0 done for success + error**; capacity not forceable on demand |
| G6 suite/ruff/mypy | pending |
| G7 Hartley ingests | pending |

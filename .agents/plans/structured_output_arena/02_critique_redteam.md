# Critique on the structured-output proposal

Date: 2026-08-19 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

### F1 — CRITICAL. The proposal never checks that a pydantic schema is one agy accepts

`model_json_schema()` emits **JSON Schema draft 2020-12 with `$defs` and
`$ref`** for any model containing a nested model or an enum — and
`knowledge_unit_extract`'s output certainly does (units carry `unit_type`,
`truth_status`, `support_roles`). The measured proof used a **hand-written flat
schema with no `$ref` at all**. The proposal then generalises from that one
sample to "the contract already owns the schema".

Gemini's structured-output support historically rejects `$ref`/`$defs` and a
long tail of keywords (`allOf`, `oneOf`, `additionalProperties`, format
specifiers). If agy passes the schema through to that API, the real contract
schema may be **rejected outright** — turning a working prose path into a hard
error for every batch.

**Required before any code:** dump `REGISTRY["curator.knowledge_unit_extract"]
.output_model.model_json_schema()`, look at it, and run agy against **that exact
schema**, not a toy. If it contains `$ref`, either flatten it or the plan needs
a different approach. This is the single measurement that decides whether the
proposal is viable, and the proposal does not include it.

### F2 — Silent behaviour change: `--output-format json` alters the whole stdout contract

`_run` currently returns `result.stdout` as the model's text. With
`--output-format json`, stdout becomes an envelope — and **every existing
consumer of `_run` now gets a different thing depending on a keyword argument**.
The proposal handles the happy path but says nothing about:

- Error envelopes. What does agy emit on `status != "SUCCESS"`? Does it still
  exit non-zero, or does it exit 0 with a failure status inside the JSON — in
  which case the existing `returncode` check silently passes a failure through?
- The capacity-exhausted path. `_raise_capacity_error` exists because agy
  reports 429 in a specific way. Is that detection still valid when stdout is an
  envelope? If it is parsed out of the text, this change breaks quota handling
  for exactly the workload that exhausts quota.
- `--print-timeout 15m` and the timeout branch.

**Required:** enumerate what the envelope looks like for success, model error,
and capacity exhaustion, from actual runs, before changing the return path.

### F3 — Raising when `structured_output` is missing turns a soft failure hard

The proposal says "do NOT silently fall back to prose" and raises. But
`AntigravityCliError` from `_run` is what propagated up and **failed the whole
job** in the incident this plan is fixing. If agy ever returns SUCCESS with a
populated `response` but no `structured_output` — plausible for a refusal, a
truncation, or a schema the backend ignored — the new code converts a batch that
the existing brace-scraper would have parsed into a job-killing exception.

That is a regression introduced by the fix, in the same failure class.

**Required:** on a SUCCESS envelope with no `structured_output`, fall back to
the `response` text and let `_parse` scrape it as it does today. Log it. The
fallback is not weakness — it is the difference between "this call was less
efficient" and "this book cannot be ingested".

### F4 — 277 temp files, and the proposal knows it

The proposal lists this under Cons and moves on. The schema for a given contract
is **identical across every batch of every run** — it is derived from a static
pydantic model. Writing it per call is pure waste and, worse, litters the repo
temp dir that `test_workspace_hygiene.py` polices.

**Required:** write once per contract per process and reuse the path, or pass
the schema as a string if agy accepts one (`--json-schema` is documented as
"schema string **or** path to a schema file" — the proposal never checks which,
despite quoting the help text).

### F5 — No test can cover this without a live CLI, and the plan does not say so

Every assertion in this proposal is about the behaviour of an external binary.
The repo's existing pattern for this is the `INCURATOR_LIVE_AGY=1`-gated live
test added in v0.56.1 (`agyPermissionLive.test.ts`). Without an equivalent, CI
green will mean "the argv we build looks right", not "agy accepts it" — which is
precisely the gap that let v0.58.0 ship a feature that never ran.

**Required:** a gated live test that runs the real contract schema through the
real CLI, plus offline tests for argv construction and envelope parsing.

### F6 — `supports_structured_output` on `FailoverClient` is undefined

`FailoverClient` wraps a primary and a fallback with different capabilities. If
the primary supports structured output and the fallback does not, what does the
wrapper report, and what happens mid-failover? The proposal does not mention the
class at all, and it is the class the vault actually runs through in some
configurations.

## 2. Suggested Alternatives

- Keep the capability flag and the optional keyword. Both are right.
- **Insert a P0 that dumps the real schema and runs it through the real CLI.**
  Viability is unknown until then; everything else is contingent.
- Fall back to prose on a missing `structured_output` (F3), and log it.
- Resolve the schema-as-string question (F4) — it removes the temp-file problem
  entirely if supported.
- Define `FailoverClient` behaviour explicitly (F6).

# Briefing: the agentic CLI answers a JSON request by running `python3`, and the sandbox kills the job

Date: 2026-08-19 | Author: main agent (measured against the live `second_brain` vault)

## 1. What happened

After v0.59.0 merged, 36 queued L2 jobs finished: **34 done, 2 failed**. The two
failures are the two largest sources in the vault.

| job | source | died at |
|---|---|---|
| 76 | `MultipleViewGeometryHartley` | batch **37 of 277**, after 29 minutes |
| 66 | `QuadricSLAM2018 - Nicholson et al.` | batch **9 of 15** |

Identical cause. Verbatim from `ingest_jobs.error`:

```
AntigravityCliError: Antigravity CLI exited 1: Error: permission check failed
for command "python3 -c '\nimport json\n\ndata = {\n  "units": [ ... ] }'"
```

and on job 66:

```
python3 -c '\nimport json, jsonschema\n\nallowed_spans = { "SPAN-7b4223bd", ... }
```

## 2. The actual mechanism

The `curator.knowledge_unit_extract` contract asks for a JSON object. Antigravity
is an **agentic** CLI: the model does not simply emit that JSON. It decides to
**write a Python program to build it** (job 76), or to **validate it against
`jsonschema` first** (job 66) — the latter prompted by our own instruction that
every emitted `source_span_id` must be in the allowed set.

Both reach for `python3 -c`. The agy permission layer does not grant that, so
the CLI exits 1. `_run_batch_with_retry` splits the batch and retries; the split
halves hit the same wall; the job fails.

**A request for text is being answered with agency, and the sandbox — behaving
correctly — converts that into a hard failure.**

This is non-deterministic: 34 jobs never took the tool route. Two of the three
largest sources are currently un-ingestable by luck.

## 3. Why the v0.56.1 precedent does not apply

v0.56.1 granted `read_file(*)` because the model legitimately needed to read a
file. Here the model needs no tool at all: the spans are in its prompt and the
answer is a string. Granting `python3` would trade arbitrary code execution for
a JSON serialiser. That is the wrong direction and the plan should not consider
it.

## 4. Measured: the CLI already has the right mode

Checked what `agy` offers before designing anything. It has **no
`--allowedTools`** (the `claude` client uses that flag; `agy` does not have it).
It does have:

```
--json-schema   Optional JSON schema string or path to a schema file to enforce
                structured output
--sandbox       Run in a sandbox with terminal restrictions enabled
--mode          accept-edits, plan
```

`--json-schema` requires `--output-format json` (it errors otherwise). Ran the
failing shape through it, deliberately including the "validate every span id"
instruction that sent job 66 to `jsonschema`:

```
$ agy -p "<extraction prompt, 2 spans>" --json-schema ku_schema.json \
      --output-format json
{"status":"SUCCESS","num_turns":1,"duration_seconds":6.85,
 "structured_output":{"units":[{...},{...}]}, ...}
```

**`num_turns: 1`.** One turn, no tool call, no permission prompt, and the parsed
object arrives in a dedicated `structured_output` field rather than having to be
scraped out of prose.

## 5. The wiring already exists end to end — one link is dropped

This is the part that decides the shape of the fix.

- `PromptContract.output_model: type[BaseModel] | None`
  (`prompting/contracts.py:44`) — a pydantic model, so `model_json_schema()`
  produces exactly the JSON Schema `--json-schema` wants.
- `PromptContract.supports_json_mode` (`contracts.py:52`) already returns
  `output_model is not None`.
- `runner.py:191` and `:203` already call
  `client.chat(messages, json_mode=contract.supports_json_mode, ...)`.
- `AntigravityCliClient.chat()` (`llm.py:932`) accepts `json_mode` and
  **ignores it** — the parameter is literally marked `# noqa: ARG002`. So do
  `ClaudeCodeClient` (`:721`) and `CodexCliClient` (`:1106`). Only
  `OllamaClient` (`:455`), `DeepSeekApiClient` (`:1261`) and `FailoverClient`
  (`:1443`) do anything with it.

So the contract knows the schema, the runner knows to ask for JSON mode, and
three CLI clients throw that knowledge away and ask an agent for prose.

Today the prose is then scraped: `_parse` (`runner.py:84`) runs `extract_json`,
a brace-matching scan over the response text, then `model_validate`.

## 6. Question for the Arena

What is the smallest change that routes structured-output contracts through the
CLI's native structured-output mode, given that `chat()` currently carries only
a **boolean** and the schema lives on the contract?

Constraints the debate must respect:

- Six client classes implement `chat()`. Whatever the signature becomes must not
  force pointless edits on the three that already work.
- `claude` and `codex` are the same shape with different flags. Decide whether
  this is a per-client capability or a client-specific path — do NOT assume the
  agy flag exists elsewhere without checking.
- The raw `response` string in the measured run carried two extra keys the
  schema never asked for (`toolAction`, `toolSummary`). `structured_output` was
  clean. Whatever is parsed must be the structured field, not the response text.
- v0.48.4, v0.55.0, and v0.56.1 were all failures at the same seam — "agentic
  CLI" versus "LLM that returns text". The RELAY has carried "prompt assembly is
  not provider-aware" as an open follow-up since v0.55.0. A fix that adds a
  fourth special case rather than naming the seam is not a fix.

# Core Proposal: carry the schema, not just a boolean

Date: 2026-08-19 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

### 1.1 Name the seam instead of adding a fourth special case

The briefing's last constraint is the design brief. Four releases have now
failed at the same place because a client that *is an agent* was handed a job
that wants *a function*. So the fix declares that difference once, as a
capability, rather than teaching each caller about each CLI:

```python
# llm.py, module level
class StructuredOutputUnsupported(Exception):
    """Raised by a client that cannot enforce a schema; callers fall back."""
```

and on every client:

```python
supports_structured_output: bool = False   # default on the base/duck contract
```

`AntigravityCliClient` sets it True. `ClaudeCodeClient` and `CodexCliClient`
stay False until someone verifies their flags — the briefing forbids assuming.

### 1.2 The signature change, minimal and backward compatible

`chat()` gains ONE optional keyword:

```python
def chat(
    self,
    messages: list[ChatMessage],
    *,
    json_mode: bool = False,
    json_schema: dict | None = None,   # NEW
    temperature: float = 0.3,
) -> str:
```

Optional with a `None` default, so the three clients that already handle
`json_mode` need no edit at all and the three that ignore it keep ignoring it
until each is done deliberately. This is the same discipline that kept
`compile_source_l2`'s 28 call sites untouched in v0.59.0.

### 1.3 The runner supplies the schema it already owns

```python
# prompting/runner.py, where json_mode is already passed
schema = (
    contract.output_model.model_json_schema()
    if contract.output_model is not None
    else None
)
client.chat(messages, json_mode=contract.supports_json_mode,
            json_schema=schema, temperature=temperature)
```

Nothing new is computed: `output_model` is a pydantic model and
`model_json_schema()` is its own serialiser.

### 1.4 The agy client uses it

```python
def _run(self, prompt: str, json_schema: dict | None = None) -> str:
    ...
    if json_schema is not None:
        schema_path = <write to the repo temp dir, alongside the log file>
        cmd += ["--json-schema", schema_path,
                "--output-format", "json"]
    ...
    if json_schema is not None:
        payload = json.loads(result.stdout)
        structured = payload.get("structured_output")
        if structured is None:
            raise AntigravityCliError(...)   # do NOT silently fall back to prose
        return json.dumps(structured)
    return result.stdout   # unchanged prose path
```

Returning `json.dumps(structured)` rather than the object keeps `chat()`'s
`-> str` contract, so `_parse`'s `extract_json` + `model_validate` still work
unchanged — on a string that is now guaranteed to be exactly the object, not
prose containing it. The measured `toolAction` / `toolSummary` keys live in the
*response text*, never in `structured_output`, so reading the structured field
is what drops them.

## 2. Pros & Cons

**Pros.**

- One optional keyword and one capability flag. No new module, no schema change.
- The contract already owns the schema; the runner already knows when JSON is
  wanted. This connects two things that exist rather than inventing a third.
- Removes the failure mode at its source: with `num_turns: 1` there is no tool
  call for a permission layer to deny.
- Also removes the brace-scraping risk class for this client — the parsed object
  is handed over rather than reconstructed from prose.

**Cons / limits.**

- `chat()` is a duck-typed interface across six classes plus test doubles; a new
  keyword means every double that uses `**kwargs`-free signatures must tolerate
  it. Optional-with-default limits but does not eliminate this.
- `--json-schema` writes a temp file per call. At one call per extraction batch
  (277 for Hartley) that is 277 temp files unless they are reused or cleaned.
- Only agy is fixed. `claude` and `codex` keep the old behaviour, so the same
  failure can recur on those backends — honestly a narrower fix than the framing
  suggests.
- Unverified at scale: the measurement was one 2-span prompt. A 277-batch book
  is the real test and has not been run.

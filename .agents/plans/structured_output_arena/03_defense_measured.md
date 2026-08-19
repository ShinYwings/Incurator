# Defense: F1 measured, and it nearly shipped a silent data-loss bug

Date: 2026-08-19 | Agent Persona: lead_architect (responding), with schema_guardian

The red_teamer refused to accept a toy schema as evidence. That refusal was
correct and it changed the design.

## 1. The real schema is not the schema that was tested

```
$ REGISTRY["curator.knowledge_unit_extract"].output_model.model_json_schema()
bytes: 1286
has $defs: True
has $ref : True
enum: 4   additionalProperties: 1
```

The measurement in the briefing used a hand-written **flat** schema. The real
one nests `ExtractedKnowledgeUnit` under `$defs` and references it by `$ref`.

## 2. What the real schema actually does — this is the finding

Same prompt, same CLI, only the schema file differs:

| schema | `status` | `num_turns` | units in `structured_output` |
|---|---|---|---|
| real (`$defs` + `$ref`) | SUCCESS | 2 | **0** |
| flattened (no `$ref`) | SUCCESS | **1** | **2** |

**The real schema does not error. It succeeds and returns nothing.** The model
took an extra turn, wrote its answer into `response` as a fenced ```json block
using **invented field names** (`knowledge_unit`, `source_span_id` — neither is
in the contract), and emitted `{"units": []}` as its structured output.

So the proposal as written would have replaced a loud crash with a **silent
empty extraction that reports SUCCESS**. Every batch would "work"; the book
would ingest to nothing. That is strictly worse than the bug being fixed, and no
test asserting "the call succeeded" would have caught it.

F1 is upheld in the strongest possible form: the viability measurement was not
optional, and the toy sample actively misled.

## 3. Flattening is the fix, and it is verified end to end

The flattened schema is not merely non-empty — it is *correct*:

```
field names: ['canonical_name', 'confidence', 'formula_centrality',
              'source_span_ids', 'statement', 'truth_status', 'unit_type']
unit_type  : observation
span ids   : ['SPAN-aaa']

KnowledgeUnitExtractOutput.model_validate(structured_output)  ->  2 units
```

The contract's own pydantic model validates the CLI's structured output
unmodified. So the pipeline is: `model_json_schema()` → **inline `$defs`** →
`--json-schema` → `structured_output` → `model_validate`.

`num_turns: 1` on the flattened path is the property that removes the incident:
one turn means no tool call, so there is nothing for the permission layer to
deny.

## 4. Consequences for the design

**D-new — the schema must be flattened before it is handed to the CLI**, and
flattening is a real step with its own edge cases (recursive models would not
terminate; `$defs` reached from more than one place must be copied, not shared).
The plan gains a phase for it with its own tests, rather than treating
`model_json_schema()` as ready to use.

**D-new — an empty `structured_output` beside a non-empty `response` is a
DEFECT SIGNAL, not a result.** This is the shape the real schema produced. The
client must detect it and refuse to report success. Combined with F3, the rule
is:

- `structured_output` present and non-empty → use it.
- `structured_output` empty/missing **and** `response` non-empty → do not trust
  the empty structure. Fall back to scraping `response` (today's behaviour, which
  works), and log loudly that structured output degraded.
- Never silently return an empty result as if the model found nothing.

F3's fallback and this rule are the same mechanism; the red_teamer's instinct
that raising was wrong turns out to matter for a reason neither of us predicted.

## 5. Conceded without argument

- **F4** — schema as string vs path. The help text says "schema string **or**
  path"; the plan will use the string form if it works, which removes the
  temp-file question entirely. Measure it, do not assume.
- **F5** — a live gated test is mandatory, following the `INCURATOR_LIVE_AGY=1`
  precedent. Section 2 above is exactly the failure an argv-only test would have
  passed.
- **F6** — `FailoverClient` must define `supports_structured_output` explicitly
  and re-evaluate per delegate on failover.
- **F2** — the envelope's error and capacity-exhausted shapes must be captured
  from real runs before `_run`'s return path changes.

## 6. Residual risk

Everything above was measured on a **2-span prompt**. Hartley is 277 batches of
real spans. Nothing here proves the model keeps choosing the one-turn path on a
dense mathematical page, and the failure that started this was itself
non-deterministic (34 of 36 jobs never took the tool route). The plan's
acceptance gate has to be a real book, not a fixture.

# Synthesis — three proposals, and the two corrections one of them forced

Proposers ran independently. A and B were each handed a shape; C was told to
attack the framing. C's job was the one that paid.

## What each argued

| | shape | cost | verdict |
|---|---|---|---|
| **A** | `derive_search_query` returns an **intent** alongside the search terms; `choose_route` reads it before the regexes | 0 extra round trips — rides the call that already runs | **adopted for case 1** |
| **B** | fuse `curator.query_search_terms` into the unused `curator.query_router` as `@v2`, so the one call returns the **route** | 0 extra round trips, but one prompt doing two jobs | **rejected as the mechanism; its spec finding stands** |
| **C** | the empty derivation *is already* the signal — route it, and stop laundering it through `(english_query or question)` | ~4 small edits, no contract moves | **adopted, and it ships first** |

## Correction 1 — the defect A and B both "found" is aimed at a dead path

A and B independently flagged `plugin_api/query_api.py:146` (`curator_query`) for
never deriving `english_query`, and both treated it as the most-used chat
surface. C checked:

- `plugin/src/context/quickQueryContext.ts:35`, in production source:
  `IncuratorClient.curatorQuery` **"had zero callers anywhere."**
- Of **96** `query_traces`: **93** are `context_fetch` only; **3** synthesised an
  answer, all dated **2026-07-08/09** — none in the 45 days since.
- `languageBridge.ts:40`, the function that would supply `englishQuery`, has no
  production caller either.

Chat and the popover both call `fetchContext` → `plugin_api/context.py`, which
**does** derive at `context.py:60`. So the shared finding is real hygiene for
MCP and the CLI, and **must not be priced as a chat fix**. Two independent agents
converging on the same wrong conclusion is exactly what the third seat is for.

## Correction 2 — "route from `question` instead of `working_query`" is dead

C measured it rather than reasoning about it:

```
briefing case 2 (derived EMPTY)         -> ('local', 'entity/fact question')
briefing case 1 (intent dropped)        -> ('local', 'entity/fact question')
ANGLE: route from `question` instead    -> ('local', 'entity/fact question')
```

The raw `question` is Korean and `_GLOBAL_SIGNALS` is English-only by contract,
so it matches nothing either way. The only way to make it match is to put Korean
back into the regex — which is v0.47.0, already reverted. **Angle closed.**

## The finding that reorders the work

The briefing treated its two rows as one bug. They are not, and their costs are
opposite. C measured both against the live vault (417 live reports, 2,362
entities, 11,248 spans):

| | `local` (today) | `global` |
|---|---|---|
| **case 1** — intent dropped, query non-empty | **33 items** (15 entity, 10 span, 8 hit), 0 reports | 10 reports |
| **case 2** — derivation returned empty | **8 items**, all raw-Korean FTS5 hits, **0 entities, 0 of 417 reports** | 10 reports, no warnings |

Case 1 is a **quality regression**: a substantial pack from the wrong corpus.
Case 2 is closer to **data loss**: near-nothing, silently.

And `global` is not a better guess for case 2 — it is the route **designed** to
work without a query. `evidence.py:341`: `if not query_terms: return
rep.get("rank", 0.0)`; `evidence.py:382` `_synthesis_items` takes no query at
all. Meanwhile `local` seeds entities from `seed_terms(query)`, and C probed the
real function: `seed_terms("")` and `seed_terms("내 볼트 전체의 주제를 정리해줘")`
both return `[]`.

## Why `(english_query or question)` is the root, for case 2

It collapses **three** states into two:

| state | arises when | today | should |
|---|---|---|---|
| derived, non-empty | normal | correct | correct |
| **derived, EMPTY** | the model says "knowledge question, nothing specific to search for" | substitutes raw `question`, **overriding the extractor's explicit finding** | route it — the question is about the corpus |
| **never derived** | CLI / MCP / tests skip the boundary | ships untranslated text into English-only internals | warn loudly |

State 2 is reachable and unambiguous at `context.py:80`, because `context.py:63`
already returned early on `is_knowledge=False`. Nothing new has to be computed.

State 3's warning is **promised and absent**: `evidence.py:193-198` says
*"`context_fetch` warns about it rather than quietly returning nothing"* — and
`context_service.py` never inspects `english_query` at all. A documented
invariant with no implementation is why A1 was misdiagnosed twice.

## Decision, and how the tiebreaker settled it

**Ship C first (this release).** Fewer moving contracts than either alternative
— no prompt version, no `SCHEMA_VERSION`, no wire format, one optional dataclass
field with a safe default. It fixes the worse failure, makes both empty states
loud, and constrains nothing downstream. The stability tiebreaker is unambiguous.

**Then A for case 1, not B.** Both cost zero extra round trips, so the tiebreaker
decides on blast radius:

- **A keeps the two jobs separate.** The model reports *what kind of question this
  is*; `choose_route` combines that with `policy.allowed_routes` and
  `GraphStatus`. Route stays a function of three inputs.
- **B hands the route itself to the model**, then gates it back. B's own con
  admits the risk it takes: larger-output contracts fail more on this provider —
  it measured `curator.community_report_write` failing **258/1,149 (22.5%)** and
  `entity_relation_extract` **43/203 (21%)** against **0/50** for the small
  `query_search_terms`. Fusing two roles into the one call every query waits on
  is the larger radius.

**B's spec finding survives its rejection**, and is filed as its own item:
`curator.query_router` is registered (`families/query.py:220`), pinned in
`test_prompt_registry.py:19` and `SYSTEM_BEHAVIOR.md:1988-1996`, promised by
`SYSTEM_BEHAVIOR.md:2119` — and has **zero production call sites**. Per CLAUDE.md
*"any divergence means both are wrong until reconciled"*: either A's intent lands
on that contract id, or the spec drops it. Not left dangling.

## Filed separately, out of scope here

**The system cannot report this class of event at all.** `query_traces` stores
`question_hash`, `prompt_runs` stores `input_hash`/`output_hash`, and
`retrieval_trace_json` records `is_cjk` and hit counts but never the query or its
emptiness. C could not measure how often case 2 fires, and said so rather than
guessing — *"absence of evidence here is largely absence of instrumentation."*
That is why this item took three diagnoses, and no proposal in this Arena
changes it.

# Briefing: the route signal is destroyed at the boundary

ROADMAP **A1**. Two prior diagnoses of this item were wrong; the measurements
below are the third and were taken end-to-end against the live vault.

## What is NOT the bug

`retrieval/router.py:41`'s `_GLOBAL_SIGNALS` is an English-only regex, and
`knowledge_value_arena` filed the item as "route selection is English-only".
That reading is wrong. `router.py:20-34` documents the English-only rule as
**deliberate** — internals are English by contract, `QueryRequest.english_query`
exists for exactly this, and **v0.47.0 already reverted** an attempt to make the
regexes multilingual: *"that fixed the symptom by making the INTERNALS
multilingual, which is the opposite of the contract."*

The boundary fix v0.47.0 shipped instead **works**: `english_query` is populated
at `plugin_api/context.py:60`.

## What the bug actually is

Measured on the live vault:

| Korean question | derived `english_query` | route |
|---|---|---|
| `2D GS가 3D보다 나은 점을 **여러 논문을 종합해서** 설명해줘` | `advantages of 2D GS over 3D` | **local** |
| `내 볼트 **전체의 주제를 정리**해줘` | *(empty string)* | **local** |

`derive_search_query` (`query.py:182`) extracts **what to search for** and
discards **what kind of question it is**. "여러 논문을 종합해서" does not survive
into the English query, so `_GLOBAL_SIGNALS` has nothing to match. The second
case returned an empty string and `working_query`'s `(english_query or question)`
fallback (`retrieval/models.py:35`) silently handed the router raw Korean.

**Adding Korean to the regex would not fix this.** An English question routed
through the same extractor loses its intent the same way — the extractor is doing
its job, and routing is reading a signal that no longer exists by the time it
looks.

## Why it costs more than a worse answer

The `local` route never consults `community_reports` (**514 exist**) or
`synthesis_nodes`. A "synthesise across my sources" question is answered from
spans alone: not a weaker answer, a **different corpus**. Nothing reports it.

## Constraints on any proposal

- Internals stay English. Do not re-open v0.47.0.
- The stability tiebreaker: fewer moving contracts, louder failures, smaller
  blast radius. It settles engineering trades — a change that makes the product
  do **less** is a product decision and goes to the user.
- A stored-contract change means its own release plus a migration rehearsal.
- The empty-`english_query` case must become an **explicit outcome**, not a
  silent fallback, regardless of which shape wins.

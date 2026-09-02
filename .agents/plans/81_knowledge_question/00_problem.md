# 00 — Problem: `is_knowledge_question` is a byproduct of translation, and the funnel guesses when it is absent

**Status**: Briefing for the Arena. Measured, not inferred.
**Roadmap item**: E8. **Release**: v0.81.0.

## The reported symptom

A message like `이 문단 번역해줘: <본문>` leaves `search_query` empty, `working_query`
falls back to the pasted body, and BM25 runs over the translation request itself —
selecting evidence for a question nobody asked.

## Why the roadmap's framing is a workaround

The roadmap says "`is_knowledge_question` gates nothing in the funnel", which
implies the fix is to make `build_evidence` conditional on it. **That would fire
only on the one path that already classifies**, and would leave two live paths
running BM25 over the pasted body exactly as before — while the query trace
would now show a gate that looks like it is working. It makes the bug harder to
see, which is worse than leaving it visible.

## Root cause, layer 1 — classification is gated on a condition chosen for translation

`is_knowledge_question` is produced only as a byproduct of `derive_search_query`.
The funnel calls that only when the question is **not already English**
(`context_service.py`):

```python
if (
    self.client is not None
    and request.english_query_status == "unset"
    and not request.english_query.strip()
    and request.question.strip()
    and not query_mod.is_probably_english(request.question)
):
```

The comment above it explains the gate honestly, and the reason is **cost**:
derivation takes 12-50 s and "buys nothing on search TERMS" for an English
question — only `intent`. That is a sound reason to skip a *translation*. It is
not a reason to skip a *classification*: a translate/summarise/rewrite request
is a non-knowledge question in any script.

**Measured** (`is_probably_english` + the funnel's own condition, no LLM needed):

| message | classified? | `is_knowledge_question` ends as |
|---|---|---|
| EN `translate this paragraph: …` | **no** | default `True` — never classified |
| KO `이 문단 번역해줘: …` | yes | the model's verdict |
| `plugin query` (language bridge supplies `english_query`) | **no** | default `True` |

## Root cause, layer 2 — the field cannot say "nobody classified this"

`ContextRequest.is_knowledge_question: bool = True`. When no classification ran,
the request **asserts** that retrieval is wanted. A consumer cannot tell a real
`True` from an absent verdict.

This repeats a lesson this codebase already paid for and wrote down.
`DerivedQuery.status` exists precisely because of it (`retrieval/models.py`):

> "A field that cannot express 'somebody tried and failed' forces the caller to
> guess, and it guessed wrong."

`status` got `derived` / `fallback` / `unset`. `is_knowledge_question` got a
bare `bool` with an optimistic default.

## Root cause, layer 3 — two implementations of one decision

- `plugin_api/context.py` classifies **unconditionally** and returns an empty
  pack with `coverage.sufficiency = "not_applicable"` when the answer is no.
  This is the popover / sidechat `fetchContext` path, and it is correct.
- The funnel classifies only for non-English input and gates on nothing.

So one path always pays and gates; the other never pays for English and cannot
gate. Two implementations of "does this need stored knowledge?" that disagree —
the shape v0.80.0's review found four times in one release.

## The mechanism that turns an empty query into damage

```python
@property
def working_query(self) -> str:
    return (self.english_query or self.question).strip()
```

An empty derived query is not empty downstream — it silently becomes the user's
entire pasted body. Any fix that stops at "skip retrieval" without addressing
this leaves the same trap for the next caller that produces an empty query.

## Decision taken by the user (2026-09-03)

**Classify at the boundary and carry the verdict into the funnel.** Boundaries
that already classify pass their result in `ContextRequest`; the funnel does not
classify on its own and, crucially, **stops inventing an answer it was not
given**. No new LLM cost. A boundary that sends no verdict must be visible in
the trace rather than silently defaulting to "yes, retrieve".

## Non-goals

- Adding an LLM call to the English funnel path.
- Changing what `derive_search_query` returns, or its prompt.
- Re-tuning BM25, fusion, or reranking.
- Touching `plugin_api/context.py`'s existing (correct) gate behaviour, beyond
  making it the single source of the verdict.

## Questions the Arena must answer

1. How is "not classified" represented so it cannot be confused with `False`,
   and what does the funnel do when it sees that state? (Refuse to retrieve, or
   retrieve and say so in the trace? Both are defensible; the standing
   tiebreaker is stability, and silently retrieving is today's bug.)
2. Which boundaries must set it, and what stops a future fifth boundary from
   forgetting — given this file's own history: "Derivation lived at ONE boundary
   from v0.47.0 and four sibling surfaces never caught up."
3. What happens to `working_query`'s fallback so an empty query stops becoming
   the pasted body?
4. What does the CLI (`wiki query`) do, where there is no plugin boundary to
   classify?

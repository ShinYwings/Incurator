# 03 — Arena: cross-critique and synthesis

Three independent proposals, then verification against the code.

## The proposals

| | shape | blast radius | enforcement |
|---|---|---|---|
| **A** minimal-surface | `bool \| None = None`, gate on `is False` | 3 files, 0 test edits | the default stops lying |
| **B** illegal-states | `KnowledgeVerdict` enum, **no default** | 6 prod + 101 test sites | `TypeError` at construction |
| **C** boundary-historian | `kw_only` tri-state string, field **renamed** | 6 prod + 101 test sites | `TypeError` at construction |

101 test call sites verified independently: `grep -rn "QueryRequest(" backend/tests/ | wc -l` → 101.

## The decisive argument

B and C both enforce "a boundary must not forget." But **forgetting is not this bug.**
The bug is that the funnel *invented* `True` for a message nobody classified. Under
A's changed default, a boundary that forgets yields `None` — which is the truth —
and the funnel does not act on a verdict nobody gave. The enforcement B and C pay
101 test edits for is solving a problem that A's one-line default change dissolves.

CLAUDE.md's standing tiebreaker is stability: *fewer moving contracts, louder
failures, smaller blast radius*. A wins on contracts and radius. It loses on
"louder failures" — and that is the one thing worth importing from C.

**Synthesis: A's shape, C's enforcement instinct, expressed as a source-tree guard
rather than a required field.** This repo already uses exactly that idiom
(`test_source_reachability_guard.py`, v0.80.0).

## The footgun A named honestly, and how the guard closes it

`None` is falsy. A future `if not request.is_knowledge_question:` would collapse
"classified no" and "nobody classified this" into one branch and silently refuse
retrieval for every ordinary CLI/MCP question. A said this is a convention, not an
invariant. The guard makes it an invariant: a test walks the source tree and fails
on any truthiness test of this field, requiring `is False` / `is True` / `is None`.

## What all three missed — verified, and it would have shipped a regression

`derive_search_query` has a provider-failure path:

```python
return DerivedQuery(terms, bool(terms), "", f"derivation unavailable: {exc}", status="fallback")
```

`is_knowledge_question` there is **`bool(terms)` — a guess, not a classification**,
and `context_service.py:741` copies it into the request verbatim. Measured against
the real function:

| message | fallback terms | `bool(terms)` |
|---|---|---|
| `이 문단 번역해줘` | `문단 번역해줘` | True |
| `A B C` | `''` | **False** |
| `L^T M(Q)L = 0` | `''` | **False** |

So with a naive gate, a provider outage on a **maths-heavy message** — which is
most of this vault — returns an empty pack whose warning says "not a knowledge
question". That is a lie about the cause and a silent loss of the answer.

C came closest, keying on `status != "unset"`, but that still trusts `"fallback"`.

**Resolution: the funnel adopts the verdict only when `derived.status == "derived"`.**
A verdict from a fallback is `None` — nobody classified, and the trace says so.
This is the same lesson `status` was created for, applied one field further.

## Decisions

- **D1** `ContextRequest.is_knowledge_question: bool | None = None`. `DerivedQuery`
  keeps a plain `bool` — a classification there always ran, so the third state
  would be meaningless.
- **D2** The funnel refuses retrieval **only** on `is False`, and returns the same
  empty-pack shape `plugin_api/context.py` already returns, so the two paths become
  one observable behaviour instead of two.
- **D3** `None` retrieves, exactly as today, and appears in the trace as `null`.
  Refusing on `None` would break every English CLI/MCP question.
- **D4** The funnel adopts a derived verdict only when `status == "derived"`.
- **D5** `plugin_api/context.py` states `is_knowledge_question=True` explicitly —
  it is the one boundary that knows.
- **D6** A source-tree guard forbids truthiness tests on the field.
- **D7** `working_query` is untouched. The gate returns before it is ever read.

## Known gap, stated rather than hidden

**English messages are still never classified**, on any path. That is the user's
own non-goal for this release (no new LLM cost on the English funnel path), and
`plugin_api/context.py` — the popover and sidechat — already classifies
unconditionally, so the surfaces a reader actually touches are covered. What
remains uncovered is an English `translate this: <body>` through `wiki query`,
the two MCP tools, or `plugin query`. This release must not be described as
fixing that.

## Phases

- **P1** `models.py`: widen the field, document the three states and `is False`.
- **P2** `context_service.py`: adopt only `status == "derived"`; add the gate.
- **P3** `plugin_api/context.py`: state the verdict explicitly.
- **P4** The source guard + regression tests, including the fallback case.
- **P5** Docs (SYSTEM_BEHAVIOR, guides EN→KR), version bump, CHANGELOG.

# Synthesis: A8 — the argument was about *where*; the defect is *what "derived" means*

Three agents: `funnel_advocate` (derive once inside `ContextService.context_fetch`),
`boundary_advocate` (derive at each surface that owns a user), and
`adversarial_verifier` (no side, test everything).

## What the Arena settled, with evidence

| claim | verdict |
|---|---|
| `context_fetch` is the single funnel | **CONFIRMED** — `choose_route` called once (`context_service.py:569`), `build_evidence` once (`:600`); nothing reaches either except through it |
| the funnel is LLM-free, so a prompt there breaks the layer | **REFUTED** — `evidence.py:220` calls `search.query(mode="hybrid", rerank=True)`, which turns on the HyDE expander (`search.py:239` → `query_expander.py:196`). A prompt already runs beneath `context_fetch`, and `search.py:236` sanctions it: *"one extra LLM call is acceptable alongside synthesis"* |
| cost of deriving in the funnel | `wiki query` **2 → 3** calls, not 1 → 2. `curator_fetch_context` is already not a pure-retrieval tool |
| `curator_explore` needs an intent | **REFUTED, measured** — `router.py:81-84` returns on explicit `mode` *before* the intent branch. `intent=""`, `"lookup"`, `"synthesis"` all yield `('explore', 'explicit --mode')`. It needs only `english_query` |
| `english_query` only affects routing | **REFUTED** — it also drives entity seeding (`evidence.py:428`), the BM25/vector query (`:472`, `:515`), and the HyDE prompt. `curator_query`'s mislabel corrupts four things, not one |
| `ContextService.client` is used | assigned (`:544`), **never read**. Derivation would be its first real use |

## The finding that reframes the item

`adversarial_verifier` found a **live bug on the shipping plugin path**, which I
then reproduced directly:

`_fallback_search_terms` (`query.py:162`) documents that it degrades to *"an
honest empty for pure non-Latin input, which the caller surfaces rather than
silently searching in the wrong language."* **It does not.** `\w` under
`re.UNICODE` keeps every script:

```
'이 논문의 전체 주제를 요약해줘'  ->  '논문의 전체 주제를 요약해줘'
'Плагин обзор'                ->  'Плагин обзор'
```

So when the provider fails, `derive_search_query` returns Korean text with
`is_knowledge_question=True`. `plugin_api/context.py:83` then sets
`status = "derived"` **unconditionally** — including on that fallback path — and
the warning at `evidence.py:443` is scoped to `"unset"`, so it is **suppressed**.

The result is silent zero-seed retrieval, with the one warning built to catch it
disabled by the caller's own claim. This is the v0.47.0 bug class, live today,
and **the funnel option would have spread it to CLI and MCP.**

The debate was about *where* to call the derivation. The defect is that its
result cannot be trusted: a fallback is indistinguishable from a real
derivation, and the field that is supposed to encode "nobody derived this"
cannot express "somebody tried and failed".

## The cost fact that decides the gate

`query.py:162-179` records a measurement: the deterministic fallback returns
**1,508 hits across the same 28 sources, with the same top results** as the LLM's
1,500 — *"for none of the LLM's 12-50 s."*

So the LLM derivation buys **nothing** on search terms. What it uniquely
produces is `intent` — and intent only changes an outcome where the English-only
route signals cannot work.

On the CLI today, `english_query` is empty, so `working_query` is **the user's own
words** (`models.py:83-84`). For an English question the regexes read what the
user actually typed — strictly better than the plugin path, which matches against
a *paraphrase* and produced eight different ones for one question. Paying 12-50 s
per query to replace real words with a sampled paraphrase is a bad trade.

For a non-English question the regexes **cannot** match, so the route is `local`
by construction, every time. That is the defect worth an LLM call.

## Locked decisions

1. **Derive in the funnel**, not at four boundaries. Four boundaries is not a
   hypothetical failure mode here — it is the measured history: derivation has
   lived at one boundary since v0.47.0 and four siblings never caught up, and
   the one that *was* filled in was filled in wrong. `boundary_advocate` conceded
   this in its own *WHERE MY POSITION FAILS*: it has "no structural defense, only
   a warning string."
2. **Gate on the question not already being English.** English questions pay
   nothing and keep routing on the user's real words; non-English questions get
   the derivation that is the only thing that can help them. This is the v0.47.0
   ruling applied, not contradicted: translate at the boundary, keep internals
   English.
3. **`status` must distinguish a fallback from a real derivation.** A third value
   is required; `"derived"` currently means "somebody assigned this string" and
   is set even when the derivation threw.
4. **The `is_knowledge_question` veto stays at the plugin boundary.** It is a
   judgment about what the user's *message* is — chat UX, not retrieval policy.
   `wiki query "translate this"` should not be silently zeroed by a
   retrieval-layer decision.

## Sequencing — two releases, lies before features

The roadmap allows one contract change per release, and there is an ordering
argument stronger than that: **do not build on fields that lie.**

- **v0.68.0 — the honesty fixes.** `status` gains a value for the fallback path;
  `_fallback_search_terms`' docstring is corrected to what it does;
  `curator_query` stops passing the raw question as `english_query` with
  `input_language="English"`. No new LLM calls, no new behaviour — it makes an
  existing silent failure loud.
- **v0.69.0 — the funnel derivation**, gated as above.

Doing these in the other order would spread the silent-failure mode to the CLI
and MCP before fixing it.

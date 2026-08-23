# Synthesis: delete the contract — and the spec sentence was pointing at a real gap

## The verdict

**Delete `curator.query_router`.** Both advocates converged, and the advocate's
own *WHERE MY POSITION FAILS* is what closes it.

`adversarial_verifier` tried to refute the safety claim on five fronts and
refuted none of them:

| probe | verdict |
|---|---|
| hidden string references (repo-wide, incl. `plugin/`, fixtures, golden files, YAML/JSON) | 7 hits, all tests/specs/one docstring. Zero in `plugin/`. `ROUTER_CONTRACT` has **no readers at all** |
| dynamic resolution — does anything sweep the registry? | `wiki prompt eval` runs a hand-listed `BUILTIN_EVAL_CASES`, not a per-contract sweep. No router fixture |
| runtime minimum-set assertion | `prompting/__init__.py:32` asserts **uniqueness only**. §15's list is prose, enforced solely by a test |
| the `role="router"` collision (3 contracts share it) | **refuted as a hazard** — `PromptRegistry` exposes `get(prompt_id)` and `list(family)`. There is no by-role lookup anywhere; `role` is a display string and a write-only DB column |
| stored data | `prompt_id` has no FK and no CHECK. **0 rows across all 29 `.sqlite` files in the repo**, including the production snapshot |

The strongest single piece of evidence is in the prompt text itself.
`ROUTER_SYSTEM` lists **`source-section` twice**, with two different
descriptions, and has since 2026-06-03. Its input model needs
`allowed_routes_block` and `graph_status_block` — two strings that **appear
nowhere else in the repository**. Nothing has ever built them. This is not
unused code; it is code that was never wired to anything.

## Why the router loses on the merits, not just on disuse

`router_advocate` argued the deterministic path really does misroute — and it is
right. `"state of"` ∈ `_GLOBAL_SIGNALS` sends *"What learning rate does the state
of the art ResNet use?"* to `global`; `how (?:might|could)` ∈ `_EXPLORE_SIGNALS`
sends *"How might I cite this paper?"* to `explore`.

But the router is the wrong instrument for those. `curator.query_search_terms@v2`
reads **the user's own words** and states intent in the *same* call that derives
search terms — 0 extra round trips — and `choose_route`'s intent branch is
authoritative over the regexes, so it fixes exactly those misroutes. The router
would read the question a second time and return a route that
`router.py::_pick` must then re-gate against `allowed_routes` and `GraphStatus`
in Python anyway.

Its two unique outputs do not survive contact either:

- `fallback_route` and `confidence` are consumed by **nothing**. That is unbuilt
  work, not existing value being discarded.
- `source-section` is unreachable on any path: **no production code sets
  `QueryRequest.source_key`**. The router could name the route but cannot supply
  the key.

## What the Arena found that the roadmap did not

The advocate's real contribution is not its position — it is the evidence it
gathered trying to defend it. **`intent` is populated at exactly one site.**

| surface | `english_query` | `intent` |
|---|---|---|
| plugin ContextService (`plugin_api/context.py:86`) | derived | derived |
| CLI `wiki query` (`query.py:377`) | `""` → `working_query` falls back to the raw question | `""` |
| MCP `curator_query` (`mcp/server.py:2031`) | `english_query=question` — the **raw question mislabeled as English** | `""` |
| MCP `curator_fetch_context` (`mcp/server.py:3255`) | absent | `""` |

`derive_search_query` is called from **one** place in the entire backend
(`plugin_api/context.py:60`).

So the v0.47.0 defect — a Korean question cannot reach `global`, because the
route signals are English-only by contract — was fixed at one boundary and is
**still live on three**. `router.py:26-35` states it was "Fixed at the boundary
instead; see `plugin_api/context.py`." That is true of one of four boundaries,
and the docstring reads as though it were all of them.

**§17's sentence was pointing at something real.** Routing *is* unreliable on
three surfaces. It just named the wrong fix: the answer is to call the
derivation that already exists at those boundaries — one call, which also
populates `english_query` — not to add a second contract that reads the question
again.

Found in passing, from the same trace: **`classify_intent_first` is accepted by
`run_query` (`query.py:424`), documented as running "intent classification
before retrieval" (`:446`), set by two callers — and never read in the body.**
`wiki query --no-intent-classify` is a no-op flag.

## Locked decisions

1. **Delete** `QueryRouterInput`, `QueryRouterOutput`, `ROUTER_SYSTEM`,
   `ROUTER_USER`, `ROUTER_CONTRACT`, and the now-orphaned `Route` alias
   (`Literal` stays — `Intent` uses it). `confidence_range` **stays**: eight
   other contracts use it.
2. **Reconcile both specs in the same change** — §15's required-id list and
   §17's opening sentence, and remove §17's "Divergence" block, which exists
   only to record this defect.
3. **Do not implement the router.** Record why, so it is not re-proposed from
   the same spec sentence.
4. **Do not fix the derivation gap in this release.** It is a separate,
   larger behavioural change on three surfaces, and the roadmap allows at most
   one contract change per release. Filed as **A8**.

## Scope exclusions / stop conditions

- No change to `choose_route`'s logic. The intent branch shipped in v0.65.0 and
  is not being revisited here.
- No new prompt contract, no new LLM call, no schema change, no migration —
  0 stored rows reference the deleted id.
- Stop and escalate if the deletion turns out to change any user-visible output
  other than one row of `wiki prompt list --family query`.

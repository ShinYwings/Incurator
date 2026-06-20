# Critique on Frontend Proposal

Date: 2026-06-21 | Agent Persona: red_teamer (Adversary) + schema_guardian + qa_runner notes

## 1. Vulnerabilities & Flaws

### A1 — Regression: multi-turn edit loop on a selection breaks
If the user pins a `line-range`, asks "fix the grammar here" (edit), the agent
opens an edit loop, and then the user follows up "actually also tighten it" — the
follow-up has a primary selection and may NOT be classified as an edit request by
`isMarkdownEditRequest` (it's a vague continuation). Under the proposal,
`latestIsLocalizedQuestion` becomes true, we strip `<edit_review_loop>`, and the
in-flight edit loop dies mid-conversation. **The proposal over-suppresses** by
ignoring `priorAnswerOpenedEditLoop` entirely.

### A2 — "Question vs edit" is doing too much work on one heuristic
Routing the whole behavior off `!latestIsMarkdownEditRequest` makes a fragile
heuristic load-bearing. If it has false negatives (misses an edit ask), the user
loses edit affordances exactly when they want them, which is a worse, more
confusing failure than the original (the original at least could edit).

### A3 — No measurable test oracle defined
"Agent must not output an edit block" is an LLM-output assertion that can't run in
CI without a live model. The plan must define a **deterministic** oracle at the
payload-assembly layer, or it cannot satisfy the Documentation & Test Mandate.

### B1 — Model override may not be threadable
The proposal assumes `convertSelectionToLatex` can pass a per-call model. If the
plugin's LLM client binds the model at construction (from `settings.model`), there
is no per-call override and the change silently uses the main model. Must verify
the client signature before promising the feature.

### B2 — `qwen2.5:0.5b` may not be installed
Defaulting the placeholder to `qwen2.5:0.5b` is fine, but if the user types it and
it isn't pulled, the conversion errors with a raw Ollama 404. Need a graceful
fallback/notice, not a crash.

### C1 — `lastUsedAt` persistence race
If two surfaces mutate `zoteroProfiles` and only one stamps `lastUsedAt`, ordering
drifts. Also: sorting must be on a COPY; sorting `settings.zoteroProfiles` in place
mutates persisted user order and could reshuffle unrelated UIs.

## 2. Suggested Alternatives

- **Fix A1+A2 (continuation safety)**: Keep the edit loop alive across a true
  continuation. Refine the predicate so suppression only happens when the turn is
  a *fresh* localized question, not a continuation of an open edit loop:

  ```ts
  const latestIsLocalizedQuestion =
    lastUserHasPrimaryContext &&
    !latestIsMarkdownEditRequest &&
    !priorAnswerOpenedEditLoop;   // don't kill an in-flight edit loop
  ```

  This narrows the fix to exactly the reported scenario: a primary selection,
  not an edit request, and NOT a continuation of an edit the assistant just
  proposed. The headline bug (early whole-doc edits poisoning a *later, separate*
  localized question) is still fixed because by then the most recent assistant
  turn is typically an answer, not an open edit — and if it genuinely is an open
  edit loop, deferring to it is the safer default.

  > Trade-off accepted: if the user is mid-edit-loop AND wants to pivot to a pure
  > question about a selection, they keep edit affordances for one extra turn.
  > That is strictly better than killing a live edit loop. Document it.

- **Fix A3 (test oracle)**: Make the suppression observable. Extract the gating
  into a pure exported helper, e.g. `shouldSuppressEditAffordances(...)` (in
  `chatContextPriority.ts` or `promptRegistry.ts`), and unit-test the predicate
  truth table directly. Additionally assert on the assembled `systemText`/messages
  that the blocks are absent/present. No live LLM needed.

- **Fix B1**: Verify the LLM client exposes a per-call model. If not, the smallest
  honest scope is to construct a transient client/config with the resolved model
  for that one call. If neither is feasible without a refactor, DEFER Item B and
  say so — do not fake it.

- **Fix B2**: On conversion failure, `Notice` the resolved model name and hint
  "run `ollama pull <model>` or clear the LaTeX-model setting." Mirror the
  existing "No models found" notice idiom in `settings.ts`.

- **Fix C1**: Sort a shallow copy (`[...profiles].sort(...)`). Centralize the
  `lastUsedAt` stamp at the single persistence/apply call site. If multiple call
  sites exist, stamp in the shared save helper, not per-UI.

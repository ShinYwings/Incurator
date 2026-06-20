# Defense / Revision

Date: 2026-06-21 | Agent Persona: system_synthesizer (Closer)

All red-team points are accepted. Resolutions folded into the Master Plan:

- **A1/A2 accepted** → predicate gains `&& !priorAnswerOpenedEditLoop`. Suppression
  now fires ONLY for a fresh localized question that is not continuing an open
  edit loop. This still fixes the reported bug: the failure case is an early
  whole-doc edit poisoning a *later separate* `Cmd+Shift+L` question, by which
  point the most-recent assistant turn is an answer (`priorAnswerOpenedEditLoop`
  false), so suppression engages exactly as intended.
- **A3 accepted** → extract a pure `shouldSuppressEditAffordances(args)` helper and
  unit-test its truth table; also assert block presence/absence on the assembled
  payload. Deterministic, no live LLM.
- **B1 accepted as a gating investigation** → P0 verifies the LLM client supports a
  per-call model override BEFORE implementing Item B. If it does not, Item B uses a
  transient resolved-model client for that one call; if even that needs a refactor,
  Item B is deferred to a follow-up and documented — not faked.
- **B2 accepted** → failure path Notices the resolved model + pull hint.
- **C1 accepted** → sort a copy; stamp `lastUsedAt` at the single shared persistence
  point.

Consensus reached. No open conflicts. Proceed to Master Plan.

---

## Human Review Override (2026-06-21) — supersedes A1 resolution above

The red-team's A1 fix (`&& !priorAnswerOpenedEditLoop`) was REJECTED on review as
counterproductive: `priorAnswerOpenedEditLoop` is true precisely in the reported
failure case (early whole-doc edit, then a fresh `Cmd+Shift+L` question), so the
clause disables suppression exactly when it is needed and the bug survives. A
fresh non-edit question must unconditionally override edit affordances; the chain
self-heals once the assistant answers without an edit. Final predicate:

```ts
const latestIsLocalizedQuestion =
  lastUserHasPrimaryContext && !latestIsMarkdownEditRequest;
```

Genuine edit continuations remain protected via `latestIsMarkdownEditRequest`.

Also overridden: B1's "defer if no override path." The TS LLM client
(`llmClient.ts`) will be extended with `complete(messages, opts?: { model?: string })`
— the no-backend rule is Python-only.

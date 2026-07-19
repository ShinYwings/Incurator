# Model Refresh Domain Analysis B: Plugin Effort and Documentation

Date: 2026-07-19

## Design Constraints From Codebase

- `bundledModelCatalogue.ts` already adapts backend JSON; no second hardcoded
  model list is needed.
- `settings.ts`, `chatSidebar.ts`, dashboard code, and `main.ts` each perform
  partial model/effort normalization.
- `llmClient.ts` always sends the stored effort, including for models whose
  catalogue declares no effort dimension.
- `PLUGIN_SCHEMA.md` documents a `supportsThinking` field that does not exist in
  `ModelOption`.

## Docs/Specs Invariants

- A model change resets to that model's declared default effort.
- UI controls must be generated from `efforts`; absent/empty means no picker and
  no provider flag.
- English guides are canonical and Korean guides must be synchronized after the
  English edits.

## Alternatives & Trade-offs

- Patch each UI independently: smallest local diffs but preserves divergent
  behavior.
- Shared pure normalizer: one small abstraction with several callers and direct
  unit tests.
- Add `supportsThinking`: redundant state that can disagree with `efforts`.
- Remove it from the spec: matches shipped code and keeps one authority.

## Final Decision

Add one pure normalizer, use it at every transition boundary, conditionally
emit effort flags, and correct the spec to the existing catalogue-driven shape.

## Implementation Pseudocode

```text
model = getModelOption(catalogue, provider, modelId)
effort = normalizeModelEffort(model, savedEffort, transitionKind)
persist effort
if effort != "": append provider effort args
```

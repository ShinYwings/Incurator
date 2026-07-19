# Plugin Proposal: One Catalogue-Driven Effort Contract
Date: 2026-07-19 | Agent Persona: Plugin Contract Engineer

## 1. Core Logic & Implementation

Treat `ModelOption.efforts` as the sole authority. Add a small pure normalizer:

```text
normalizeEffort(model, stored, resetToDefault):
  if model.efforts is empty: return ""
  if resetToDefault: return model.defaultEffort or model.efforts[0]
  if stored is supported: return stored
  return model.defaultEffort or model.efforts[0]
```

Use it for settings model/provider changes, sidebar model changes, dashboard
changes, and load-time catalogue migration. A deliberate model change resets
to the chosen model's default; loading preserves a still-valid stored value.

Expand the Codex TypeScript effort union with `max` and `ultra`. Allow the
persisted Claude effort slot to represent no effort (`""`). Build provider CLI
arguments conditionally: omit Claude `--effort` and Codex
`model_reasoning_effort` when the normalized value is empty.

Reconcile `PLUGIN_SCHEMA.md` with the actual `ModelOption` shape by removing the
fictional required `supportsThinking` field and documenting optional
`efforts`/`defaultEffort`.

## 2. Pros & Cons

Pros: all plugin surfaces obey one rule and no-effort models are executable.
Cons: an old saved model may change effort once during migration; tests and the
changelog must make that behavior visible.

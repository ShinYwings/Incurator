# Critique on D_models
Date: 2026-09-10 | Agent Persona: Frontend Runtime Reviewer

## 1. Vulnerabilities & Flaws

- Merely removing retired Gemini 3.5 from the catalogue can leave saved `settings.model` set to the retired ID, so the user's existing installation continues failing after update even though a fresh install passes tests. Preserving valid and custom selections is correct; preserving a positively verified retired ID without explanation does not finish this request.
- Defaults are positional in this catalogue. Inserting a model at the front changes new-install behavior and may also affect invalid-choice normalization. Audit both paths and document the selected replacement rather than treating an insertion as display-only.
- Codex cache context limits and API limits differ; the proposal correctly preserves CLI limits. Effort options must likewise come from the same CLI snapshot to avoid rendering an unsupported default after provider/model switching.

## 2. Suggested Alternatives

- Exact-match normalization of verified retired bundled IDs to their same-provider current default is a small, deterministic settings migration. Preserve all other explicit IDs, especially `custom` IDs absent from this release's static list. Alternatively explicitly block the retired choice with an actionable replacement state, but that adds UI and another user step.
- Tests: load saved Gemini 3.5, valid older supported Gemini, unknown custom Gemini; verify only the retired one changes and effort normalizes with replacement. Confirm backend defaults and plugin defaults agree on new installations.
- Keep network validation out of interactive send and model switching; the static catalogue is the right latency-preserving mechanism.

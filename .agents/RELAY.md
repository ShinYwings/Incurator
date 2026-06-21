# Cross-Agent Relay State

## Status: IDLE (v0.22.0 implemented; PR #45 in review)

v0.22.0 shipped to PR #45 on `feature/chat-decay-quick-wins` (one combined release):
- Dedicated PDF-extraction vision models (`llm.vision_model` always-on `add source`
  page-VLM → LaTeX L1; `latex_extract_model` light slot; CLI-subscription cloud
  vision, no API keys; Dashboard rows). SYSTEM_BEHAVIOR §26.2a.
- Chat-decay localized-question edit-affordance suppression (`Cmd+Shift+L`).
- Zotero import-profile recent-first ordering.
- The unreleased v0.21.0 `latexModel` was reshaped into the vision slots.

Known follow-up: routing the plugin's interactive Convert-to-LaTeX / Cmd+Shift+X
through `latex_extract_model` (today they use the main chat model; the dedicated
models are honored at the backend ingest layer).

Next roadmap priority: Prompt Architecture Overhaul & Refactoring.

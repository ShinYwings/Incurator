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

### Update (2026-06-21, Codex)

Addressed PR #45 review fixes on `feature/chat-decay-quick-wins`:
- Persist existing Zotero profile `lastUsedAt` immediately after selection so MRU order survives reload even if import later fails.
- Route interactive PDF extraction through backend `wiki plugin pdf transcribe`:
  - right-click Convert-to-LaTeX uses backend-resolved `latex_extract_model → vision_model → main-if-vision`;
  - Cmd+Shift+X crop writes a temp PNG, calls the same backend resolver, sends successful transcription as chat text, and does not forward the crop image to the main chat model's vision path.
- Scope `ollama pull` failure hints to active Ollama provider by stripping them from PDF extraction fallback notices for non-Ollama active providers.
- Keep page-VLM ingest concurrency serial for agentic CLI vision providers; only Ollama opts into concurrent page calls.
- Updated `CHANGELOG.md`, plugin guide EN/KR, plugin/system specs, and cleared the completed PDF extraction inbox item from `.agents/USER_REPORT.md`.

Validation completed:
- `scripts/backend-check pytest` → 1012 passed, 6 skipped, 5 xfailed.
- `scripts/backend-check ruff` → passed.
- `scripts/backend-check mypy` → passed.
- `npx vitest run -c ./vitest.config.ts` from `plugin/` → 55 files, 511 tests passed.
- `VAULT_ROOT=testbed wiki status` → exit 0; existing warning remains: vault schema v0, backend expects v1.

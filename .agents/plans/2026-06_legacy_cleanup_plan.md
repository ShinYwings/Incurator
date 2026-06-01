# Goal: Remove Legacy Gemini Fallback and Backward Compat Logic

The user requested the removal of legacy remnants related to the `gemini` fallback logic, including the auto-selection for `< 16GB RAM` machines and the backward compatibility capacity fallback chain for Antigravity CLI models.

## Proposed Changes

### Configuration
- **`backend/pyproject.toml`**: Remove the `[project.optional-dependencies] gemini` block and the `google-generativeai` dependency entirely.

### LLM Client Layer (`backend/src/curator/llm.py`)
- **Delete `_get_antigravity_fallback_chain()`**: Remove the function that falls back from "lite" to "flash" to "pro" Gemini models.
- **Refactor `AntigravityCliClient._run`**:
  - Remove the `for current_model in models_to_try:` loop.
  - Remove the capacity exhaustion (429) retry logic.
  - Simplify it to run the CLI once using `self.model`.
- **Update Docstrings**: Remove the legacy references to `auto + RAM < 16 GB → antigravity-cli client` in `build_client`.

## Verification Plan
- Run `uv sync` to update the virtualenv.
- Run `uv run pytest tests` to verify that the removal of `_get_antigravity_fallback_chain` doesn't break any core flows.

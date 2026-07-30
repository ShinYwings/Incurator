# Defense and Revision: Antigravity Prompt Transport

Date: 2026-07-30 | Agent Persona: System Synthesizer

## 1. Resolved concerns

- Backend Antigravity prompts are already bounded to 18,000 characters per
  generation chunk; the hotfix does not expand that limit.
- `get_default_effort()` returns an empty string for custom/no-effort models, so
  the flag can remain conditional.
- Integration coverage will exercise the existing interactive normalizer and
  JSON response in addition to the lower-level command construction.
- No content heuristics will be introduced. The reported narration disappears
  because the model receives the intended prompt.

## 2. Consensus

Implement the shared transport correction, preserve every surrounding
provider/error/clipboard contract, and prove the real CLI path after unit and
full-suite validation.

# RELAY — v0.36.8 PDF Convert-to-LaTeX Hotfix

## Goal

Restore the PDF viewer's Convert-to-LaTeX action so selected text is preserved
and rendered mathematics is returned as LaTeX, never Antigravity scratch-agent
planning narration.

## Plan Reference

- Branch: `hotfix/v0.36.8-latex-transcribe`
- Draft PR: `https://github.com/ShinYwings/Incurator/pull/96`
- Active review follow-up plan:
  `.agents/plans/02_v0368_latex_model_dispatch_followup.md`
- Active evidence ledger:
  `.agents/plans/02_v0368_latex_model_dispatch_evidence.md`

## Analysis & Reasoning

- Reproduced the report with the deployed backend command and current
  `antigravity-cli::gemini-3.6-flash` extraction model.
- `AntigravityCliClient._run()` passes the real prompt through stdin and gives
  `agy --print` only “Follow the instructions in the provided input.”
- Installed `agy 1.1.8` does not consume that stdin as the print prompt, so it
  explores its scratch workspace and returns progress narration.
- The backend also embeds the selected model as a prompt hint instead of using
  the now-supported `--model` / `--effort` flags.
- A direct `agy --model gemini-3.6-flash --effort medium --print <full prompt>`
  returned the expected `<transcription>` block.
- PR #96's first fresh Backend CI resolve installed `mcp==2.0.0`, whose removal
  of `mcp.server.fastmcp` failed mypy before pytest. The supported SDK contract
  is now pinned to MCP 1.x in both `mcp` and `dev` extras; a fresh isolated
  install resolved `mcp==1.29.0`, imported FastMCP, and passed mypy.
- After the dependency boundary fix, both Backend CI jobs, both Plugin CI jobs,
  and Version Consistency passed on PR #96.
- User review found that the dedicated extraction task should use low effort
  when supported and requested a simplification review.
- The review confirmed that the plugin Antigravity command passes effort but
  omits the selected model, the backend extraction task inherits general
  catalogue defaults, and the Antigravity Opus catalogue slug is stale.
- The follow-up now selects low once at the explicit extraction boundary,
  preserves main-model effort on the final fallback, forwards the plugin chat
  model, and corrects fixed Antigravity Claude variants.
- Live backend calls passed for all five Antigravity vision models and Codex
  Terra; Claude Code is logged out and no Ollama vision model is installed.

## Progress Status

- [x] Reproduce the clipboard payload through `wiki plugin pdf transcribe`.
- [x] Confirm the installed Antigravity CLI argument contract.
- [x] Confirm a corrected direct call returns original text plus LaTeX.
- [x] Update docs/specs.
- [x] Add failing tests.
- [x] Implement backend prompt/model/effort forwarding.
- [x] Run focused, full CI, and testbed smoke validation.
- [x] Bump v0.36.8, update changelog, and remove plan artifacts.
- [x] Push and open draft PR #96.
- [x] Push the MCP 2.0 compatibility follow-up and confirm rerun CI.
- [x] Capture and plan the PR #96 model-dispatch review follow-up.
- [x] Add failing backend/plugin dispatch tests.
- [x] Implement task-scoped low effort, exact model IDs, and plugin model forwarding.
- [x] Re-run full validation and complete the code review.

## Critical Context / Blockers

- No blocker.
- The worktree was clean at branch creation.
- Rollback anchor: `a26890535a243b272cb8f01b3332e36297381556`.
- Current active testbed exists and was used for the reproduction command.
- Backend: 1,276 passed; ruff and mypy passed.
- Plugin: 721 passed; production build passed.
- Testbed lint: 100/100.

## Immediate Next Action

Record the validation commit, delete completed plan artifacts, push the branch,
update PR #96, and confirm CI.

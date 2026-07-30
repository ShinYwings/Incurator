# RELAY — v0.36.8 PDF Convert-to-LaTeX Hotfix

## Goal

Restore the PDF viewer's Convert-to-LaTeX action so selected text is preserved
and rendered mathematics is returned as LaTeX, never Antigravity scratch-agent
planning narration.

## Plan Reference

- Branch: `hotfix/v0.36.8-latex-transcribe`
- Master plan: `.agents/plans/02_latex_transcribe_hotfix.md`
- Evidence: `.agents/plans/02_latex_transcribe_hotfix_evidence.md`

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

## Progress Status

- [x] Reproduce the clipboard payload through `wiki plugin pdf transcribe`.
- [x] Confirm the installed Antigravity CLI argument contract.
- [x] Confirm a corrected direct call returns original text plus LaTeX.
- [x] Update docs/specs.
- [x] Add failing tests.
- [x] Implement backend prompt/model/effort forwarding.
- [x] Run focused, full CI, and testbed smoke validation.
- [ ] Bump v0.36.8, update changelog, remove plan artifacts, push, and open PR.

## Critical Context / Blockers

- No blocker.
- The worktree was clean at branch creation.
- Rollback anchor: `a26890535a243b272cb8f01b3332e36297381556`.
- Current active testbed exists and was used for the reproduction command.

## Immediate Next Action

Bump v0.36.8, delete the shipped hotfix plan artifacts, run version consistency,
then push and open the PR.

# v0.36.8 PDF Convert-to-LaTeX Evidence Ledger

Date: 2026-07-30
Status: IMPLEMENTED AND VALIDATED
Master Plan: `.agents/plans/02_latex_transcribe_hotfix.md`

## 1. Rollback anchor

- Base branch: `master`
- Base commit: `a26890535a243b272cb8f01b3332e36297381556`
- Hotfix branch: `hotfix/v0.36.8-latex-transcribe`
- Pre-branch worktree: clean
- Data/schema migration: none

## 2. Current contract reality

- Plugin calls `wiki plugin pdf transcribe --text <selection>` and copies only
  the returned `latex` field.
- Backend selects the dedicated model and uses a strict
  `<transcription>...</transcription>` prompt.
- Backend normalizes tagged output before emitting JSON.
- `AntigravityCliClient._run()` alone loses the prompt: it sends a generic
  `--print` argument and places the real prompt on stdin.
- The same client does not use the current CLI's model/effort flags.

## 3. Pre-change reproduction

- Installed CLI: `agy 1.1.8`.
- Active extraction model: `antigravity-cli::gemini-3.6-flash`.
- Active primary effort: `medium`.
- Testbed exists.
- Live backend command returned `ok: true` and scratch-agent narration beginning:
  “I will start by checking the current permissions...”
- A direct corrected invocation returned:
  `The reconstruction loss is $L = \sum_i (x_i - y_i)^2$.`

## 4. Post-change validation

- Focused backend tests:
  `27 passed in 0.24s` for `test_v021_models.py` and
  `test_plugin_pdf_transcribe.py`.
- Live Antigravity transcription through the real backend command:

  ```json
  {
    "ok": true,
    "latex": "The reconstruction loss is $L = \\sum_i (x_i - y_i)^2$.",
    "model": "gemini-3.6-flash"
  }
  ```

- Full backend pytest: `1273 passed, 6 skipped, 5 xfailed`.
- Ruff: all checks passed.
- mypy: no issues in 125 source files.
- Plugin Vitest: 68 files / 721 tests passed.
- Plugin production build: passed.
- Testbed `wiki status`: command completed; existing fixture schema-v0 migration
  notice remains unrelated.
- Testbed `wiki lint`: 100/100, 0 errors, 0 warnings, 0 infos.
- Version consistency: pending the final `0.36.8` release bump.

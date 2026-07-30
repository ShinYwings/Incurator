# v0.36.8 Model Dispatch Evidence Ledger

Date: 2026-07-30

## Rollback Anchor

- Branch: `hotfix/v0.36.8-latex-transcribe`
- Commit before follow-up: `0b82d8a0aa74b09f2157e0c848b53b13ad90aa54`
- Draft PR: `https://github.com/ShinYwings/Incurator/pull/96`

## Current Contract Reality

- `agy 1.1.8` exposes Gemini base slugs with low/medium/high variants.
- `agy 1.1.8` exposes `claude-sonnet-4-6` and
  `claude-opus-4-6-thinking` as fixed variants.
- The plugin Antigravity CLI command currently omits the selected model.
- The backend extraction resolver currently creates explicit clients without a
  task effort, causing the Antigravity transport to fall back to general
  catalogue defaults.

## Pre-Validation

- PR #96 CI is green before this follow-up.
- Live Gemini 3.5 Flash, Gemini 3.6 Flash, and Gemini 3.1 Pro low-effort
  transcription calls returned the requested transcription block.
- Live fixed Sonnet and corrected fixed Opus calls returned the requested block
  with no effort flag.
- Current catalogue Opus slug failed as unrecognized.
- Claude Code live extraction remains authentication-blocked; code-path tests
  remain available.
- No installed Ollama vision model is available for live extraction; code-path
  tests remain available.

## Post-Validation

- Focused backend: 45 passed.
- Focused plugin: 73 passed.
- Backend full suite: 1,276 passed, 6 skipped, 5 expected failures.
- Backend ruff: passed.
- Backend mypy: passed across 125 source files.
- Plugin full suite: 721 passed.
- Plugin production build: passed.
- Testbed lint: 100/100.
- Live `wiki plugin pdf transcribe`: returned
  `The reconstruction loss $L = \sum_i (x_i - y_i)^2$.` through
  `gemini-3.6-flash`.
- Live backend extraction resolver:
  - `gemini-3.5-flash`: low, passed.
  - `gemini-3.6-flash`: low, passed.
  - `gemini-3.1-pro`: low, passed.
  - `claude-sonnet-4-6`: effort omitted, passed.
  - `claude-opus-4-6-thinking`: effort omitted, passed.
  - `codex-cli::gpt-5.6-terra`: low, passed with the production prompt.
- Claude Code CLI is installed but not authenticated; live provider validation
  is blocked by `loggedIn: false`. Its resolver/factory/command paths are covered
  by tests.
- Installed Ollama models are text-only (`qwen2.5:3b`, `qwen2.5:0.5b`,
  `bge-m3`), so no live Ollama vision extraction was possible. Its independent
  client/fallback path remains covered by tests.

## Code Review Findings

All findings are resolved:

1. **Selected plugin model did not reach Antigravity.** The command builder
   forwarded effort but omitted `--model`; it now passes both.
2. **Task policy was inferred in the shared transport.** Explicit extraction
   slots now choose low at the extraction boundary only; shared chat and ingest
   defaults are unchanged.
3. **Antigravity Opus ID was stale.** The catalogue now uses the live
   `claude-opus-4-6-thinking` slug.
4. **Fixed variants advertised a fake effort.** Antigravity Claude variants no
   longer expose `thinking` as a selectable `--effort`.
5. **Comments still described prompt hints.** Backend comments now match the
   provider-native `agy --effort` transport.

No blocking or actionable review finding remains in the combined PR diff.

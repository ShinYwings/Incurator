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

Pending implementation.


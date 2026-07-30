# PR #96 Review Follow-up Briefing

Date: 2026-07-30

## User Report

The user asked whether the other selectable models actually work, proposed
using only low effort for Convert-to-LaTeX, and requested a code review focused
on logic that solves simple problems indirectly.

## Measured Problems

1. The plugin Antigravity command builder passes `--effort` but not the selected
   `--model`, so the model selector does not control the spawned `agy` process.
2. The backend's dedicated LaTeX slot has no task effort policy. Its independent
   client is created without effort and the shared Antigravity transport later
   guesses the catalogue default (`medium` or `high`).
3. The Antigravity catalogue advertises `claude-opus-4-6`, while the installed
   `agy 1.1.8` exposes `claude-opus-4-6-thinking`.
4. Antigravity fixed-thinking Claude variants are represented as if `thinking`
   were a valid `--effort` value, although the CLI accepts only
   `low|medium|high`.

## Required Outcome

- Chat model selection reaches `agy --model`.
- An explicit `latex_extract_model` or its explicit `vision_model` fallback
  uses `low` when the selected catalogue model declares it; otherwise it omits
  effort.
- A main-chat client used only as the final fallback retains its user-selected
  effort rather than being mutated.
- Catalogue IDs and effort dimensions match the live CLI.
- Focused and full backend/plugin tests pass.


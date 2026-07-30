# Critique on Backend Prompt Transport Proposal

Date: 2026-07-30 | Agent Persona: Regression / Security Reviewer

## 1. Vulnerabilities & flaws

- Moving prompts from stdin to argv creates a theoretical argument-size limit.
- Adding flags unconditionally could break custom Antigravity model IDs with no
  effort dimension.
- Fixing only the command builder does not prove the user-visible JSON path
  returns normalized text.
- A broad output sanitizer for “I will” lines would corrupt legitimate PDF prose.

## 2. Suggested alternatives

- Retain the existing `optimal_chunk_chars = 18000`, far below the platform
  argument limit, and add no new large-prompt path.
- Resolve effort through the existing catalogue and omit `--effort` when no
  catalogue effort exists.
- Add both command-construction tests and a focused `plugin pdf transcribe`
  normalization test.
- Keep normalization content-agnostic; fix transport rather than filtering
  arbitrary English sentences.

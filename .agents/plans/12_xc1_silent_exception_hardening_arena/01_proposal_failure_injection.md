# Test Engineer Proposal: Failure Injection at Owned Seams
Date: 2026-07-19 | Agent Persona: Test Engineer

## 1. Core Logic & Implementation

Add failing tests before each component change:

- command helpers: corrupt build manifest, failed optional installer/auth launch,
  persona evolution parse/LLM failure, and model retry failure;
- MCP: invalid curate path, optional suggestion/worker/model provisioning
  failures, JSON extraction, and client close failure;
- plugin API: topic-classification failure with deterministic slug fallback.

Add one AST source-policy test that rejects a silent broad handler unless its
line is in a small reviewed allowlist with a reason. Prefer behavior assertions
over source-string replacements.

## 2. Pros & Cons

Pros: proves fallback compatibility and makes future regressions visible. Cons:
some third-party failure types are not stable, so those seams need logging with a
justified broad catch rather than brittle exception tuples.

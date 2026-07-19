# Critique on the Model Refresh Proposals
Date: 2026-07-19 | Agent Persona: Red Team / Compatibility Auditor

## 1. Vulnerabilities & Flaws

- API model pages are not the runtime contract. Copying a 1.05M OpenAI API
  context window into this CLI-backed catalogue would conflict with Codex's
  current 272K effective cache value.
- `claude-sonnet-5` is current in the API documentation but is not verified as a
  full ID in the installed Claude Code runtime. Adding it now would violate the
  static spec's no-phantom-model rule.
- PL-1 explicitly excludes model/provider behavior. Combining it with this
  change would make failures difficult to attribute and invalidate its plan.
- Removing stale models triggers `main.ts` load-time migration. Without a test,
  users can get an invalid effort or an unexplained model reset.
- Context numbers are tokens, but chat truncation is characters. Raising a
  catalogue context must not silently promise a tokenizer-accurate prompt
  budget.
- `ultra` can authorize automatic delegation in Codex. It must be documented as
  distinct from ordinary increased reasoning depth.

## 2. Suggested Alternatives

- Use local CLI discovery/cache as the executable source and official vendor
  docs as semantic corroboration.
- Keep the currently visible previous Codex model (`gpt-5.5`) for one migration
  window; remove hidden or absent entries.
- Keep Sonnet 4.6 and Haiku 4.5, add only verified Claude Code full IDs (Fable 5
  and Opus 4.8), and do not guess Sonnet 5 support.
- Add load/migration and exact command-vector tests before changing runtime
  defaults.
- Defer PL-1 to v0.36.0 and token-aware context accounting to its own bounded
  bug plan.

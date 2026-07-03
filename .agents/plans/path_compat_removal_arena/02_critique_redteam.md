# Critique on Current-Contract-Only Path Resolution
Date: 2026-07-04 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

- Removing the converter before repairing `second_brain` strands the local DB.
- Removing named-root resolution would break generic external references; only
  legacy root-array conversion may be deleted.
- A repo-wide deletion of every item labeled "legacy" would conflate historical
  migrations, current fallbacks, and unrelated public contracts.
- Tests must ensure the CLI group and legacy schema symbols are absent, not just
  stop exercising them.

## 2. Suggested Alternatives

Constrain scope to path-format compatibility, preserve current resolvers, make
rollout order an explicit gate, and add source-inspection tests that reject
reintroduction of the command/module/schema converter.

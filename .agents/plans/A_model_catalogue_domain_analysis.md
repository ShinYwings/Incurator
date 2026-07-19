# Model Refresh Domain Analysis A: Backend and CLI Runtime

Date: 2026-07-19

## Design Constraints From Codebase

- `backend/src/curator/data/models.json` feeds backend commands, MCP output, and
  the bundled plugin catalogue.
- `constants.py` still defaults to `gpt-5.5`; help text and tests embed the same
  stale example.
- Incurator launches `claude` and `codex` subscription CLIs. API-only model
  availability is insufficient evidence.

## Docs/Specs Invariants

- `SYSTEM_BEHAVIOR.md` forbids phantom catalogue entries.
- Empty effort means use the CLI default; non-empty effort must be passed using
  the provider-native control.
- A minor bump requires all four static spec titles to move to the v0.35 line.

## Alternatives & Trade-offs

- API-first catalogue: newest names, but can expose models the installed CLI
  cannot run.
- CLI-first catalogue: executable and testable, while potentially lagging an
  API-only announcement.
- Keep all legacy IDs: avoids migration but preserves known hidden/absent
  choices.

## Final Decision

Use the installed CLI/cache as the executable contract, retain only visible
legacy GPT-5.5 for one migration window, and add exact invariant/command tests.

## Implementation Pseudocode

```text
read models.json
replace claude/openai entries with locked tables from Arena consensus
update default constants and examples
test ids/order/context/efforts/defaults
test CLI command vectors for every new effort edge
```

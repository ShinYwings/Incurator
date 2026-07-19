# Backend Proposal: CLI-Verified Canonical Catalogue
Date: 2026-07-19 | Agent Persona: Backend / Model Catalogue Guardian

## 1. Core Logic & Implementation

Keep `backend/src/curator/data/models.json` as the sole catalogue. Replace
phantom/hidden entries with the models visible to the installed subscription
CLIs, then make constants and command examples agree with the first/default
entry.

Codex contract:

| Model | Context | Efforts | Default |
|---|---:|---|---|
| `gpt-5.6-sol` | 272000 | low, medium, high, xhigh, max, ultra | low |
| `gpt-5.6-terra` | 272000 | low, medium, high, xhigh, max, ultra | medium |
| `gpt-5.6-luna` | 272000 | low, medium, high, xhigh, max | medium |
| `gpt-5.5` | 272000 | low, medium, high, xhigh | medium |

Claude Code contract:

| Model | Context | Efforts | Default |
|---|---:|---|---|
| `claude-sonnet-4-6` | 1000000 | low, medium, high, max | high |
| `claude-fable-5` | 1000000 | low, medium, high, xhigh, max | high |
| `claude-opus-4-8` | 1000000 | low, medium, high, xhigh, max | high |
| `claude-haiku-4-5` | 200000 | none | none |

Use `gpt-5.6-sol`/`low` as the Codex default. Retain Sonnet 4.6 as the routine
Claude default but align its default effort with the current CLI contract.

Add invariant tests for unique IDs, catalogue order/default agreement,
`default_effort in efforts`, exact current IDs, and command propagation for
`max`/`ultra`.

## 2. Pros & Cons

Pros: the picker matches the actual CLI runtime, hidden models disappear, and
defaults are deterministic. Cons: removing stale full IDs migrates affected
saved selections to the provider default; this must be explicit in release
notes and covered by migration tests.

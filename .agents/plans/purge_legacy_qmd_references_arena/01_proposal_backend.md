# Backend Proposal: Remove Runtime Compatibility Shims

Date: 2026-06-20 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

- Rename `_refresh_qmd_index` to `_refresh_search_index` and update all call
  sites and tests.
- Replace user-visible messages that say the system is indexing qmd with
  DB-native search wording.
- Update MCP docstrings and comments to describe DB-native search.
- Remove `qmd_binary`, `qmd_ready`, and `qmd_version` from
  `curator_status` and runtime status snapshots.
- Remove the qmd install hook from `scripts/build/hatch_build.py`.
- Rename query-expander internals from qmd-specific names to generic structured
  expansion names while preserving the `lex:`, `vec:`, and `hyde:` wire grammar.
- Replace qmd URI cleanup with scheme-generic legacy URI stripping where needed,
  avoiding a literal qmd dependency in active code.

## 2. Pros & Cons

Pros:
- Removes misleading runtime surfaces that can steer agents back to a retired
  binary.
- Keeps DB-native search implementation unchanged.
- Gives CI a permanent guard against regression.

Cons:
- Removing `qmd_*` status keys can break very old plugin builds or external
  clients still reading those compatibility fields. The current plugin already
  prefers `search_*`, so this branch should migrate the remaining fallbacks.


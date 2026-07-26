# Defense And Consensus
Date: 2026-07-26 | Agent Persona: System Synthesizer

## 1. Response To Critique

The proposal is revised to:

- prefer build fingerprint comparison and fall back to version comparison;
- require a complete artifact copy before exposing reload;
- reload the renderer through the supported app command, not internal
  disable/enable calls;
- separate `isVisible`, user override, and materialized prompt content;
- use exact source/page context keys;
- keep hidden contexts identity-only and eye-off until materialization succeeds;
- retain all v0.36.4 permission security constraints.

## 2. Consensus

The hotfix is a patch because it restores existing update, open-tab, and
headless-read contracts without a new setting, command, schema, or durable data
format. The currently running Obsidian instance must be reloaded once to activate
the already installed v0.36.6 bundle; v0.36.7 prevents future on-disk/runtime
drift from failing silently.


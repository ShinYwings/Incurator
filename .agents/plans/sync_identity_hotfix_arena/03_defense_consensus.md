# Defense and Consensus
Date: 2026-07-04 | Agent Persona: system_synthesizer

## 1. Resolved Design

- Use a SHA-256 vault-root namespace under backend-local cache.
- Keep transport filenames and JSONL schema unchanged.
- Ignore, rather than migrate, vault-local `sync_state.json`.
- Preserve the old shared JSONL during recovery.
- Test separate cache roots against one simulated synced transport.

## 2. Release Decision

This is a patch hotfix: no public command, DB schema, JSONL schema, or plugin
setting changes. Documentation changes correct the machine-local state
location. Release version is `0.32.1`.

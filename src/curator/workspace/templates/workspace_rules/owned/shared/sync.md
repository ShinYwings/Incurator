# Rule Synchronization

The files under `.agents/curator/` are managed by llm-wiki.

- Shared behavior belongs in `.agents/curator/shared/rules.md`.
- Runtime-specific files should only add runtime instructions.
- Top-level agent files may contain local notes outside the llm-wiki managed block.
- Re-run workspace provisioning when these templates change.


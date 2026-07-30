# Defense and Consensus
Date: 2026-07-30 | Agent Persona: System Synthesizer

## 1. Resolved Design

The critique is accepted. The implementation will:

1. Add `get_backend_model_efforts(backend_key, model_id)` to the catalogue API.
2. Extend `make_client_for` with a keyword-only `effort` value; it will not
   infer task policy.
3. Resolve the first explicit extraction slot once and pass `low` only when the
   catalogue declares it.
4. Preserve the existing main client as the last fallback.
5. Add `--model <selected>` to the plugin Antigravity command.
6. Correct the Opus slug and remove fake `thinking` effort dimensions from
   Antigravity Claude variants.

This keeps policy at the caller, transport at the client, and capability facts
in the catalogue.


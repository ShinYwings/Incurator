# Model Dispatch Domain Analysis

Date: 2026-07-30

## Design Constraints from the Codebase

- `models.json` is the single model catalogue used by backend and plugin UI.
- Persisted dedicated model slots use `backend_key::model_id`.
- `make_client_for` builds independent clients for `vision_model` and
  `latex_extract_model`.
- `_resolve_vision_client` is full-page ingest policy and must never consult the
  light LaTeX slot.
- `_resolve_extract_client` is interactive Convert-to-LaTeX policy and may
  select the LaTeX slot, vision slot, or main vision-capable client.
- The main client can be a failover client; it must not be mutated.

## Specs and Guide Invariants

- Selected prose must be preserved and rendered math converted to LaTeX.
- Provider progress narration is not successful transcription output.
- The exact selected CLI model must be passed through provider-native controls.
- Unsupported effort flags must be omitted.

## Alternatives and Trade-offs

1. Force low in the Antigravity client: smallest diff, wrong scope.
2. Clone or mutate the main client: obscures failover semantics and leaks state.
3. Add a task-policy flag to every client: speculative abstraction.
4. Pass a checked effort into the existing independent-client factory:
   smallest scoped design that works across providers.

## Final Decision

Use alternative 4 for explicit extraction slots. Keep the final main-client
fallback unchanged. Correct the shared catalogue and plugin command dispatch.

## Implementation Pseudocode

```text
selected_slot = latex_extract_model if nonempty else vision_model
if selected_slot:
    provider, model = split(selected_slot)
    supported = catalogue.lookup_by_backend_key(provider, model).efforts
    effort = "low" when supported contains "low", otherwise ""
    client = make_client_for(selected_slot, config, effort=effort)
    require vision capability and return
return main_client when vision-capable, otherwise None
```


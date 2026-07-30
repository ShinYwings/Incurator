# Model Dispatch Proposal: Decide Once at the Task Boundary
Date: 2026-07-30 | Agent Persona: Lead Architect

## 1. Core Logic & Implementation

Keep the shared Antigravity transport generic. Add an optional `effort`
argument to the existing independent-client factory, and have the
Convert-to-LaTeX resolver choose the explicit extraction model once:

```python
selected = latex_extract_model or vision_model
if selected:
    efforts = catalogue_efforts_for_backend(selected.provider, selected.model)
    effort = "low" if "low" in efforts else ""
    return require_vision(make_client_for(selected, effort=effort))
return main_client if main_client.supports_vision else None
```

The plugin's Antigravity command builder must emit both `--model` and the
already-normalized optional `--effort`.

Correct the fixed Antigravity Claude catalogue entries so their thinking mode
is encoded only in their model slugs and no invalid effort selector is shown.

## 2. Pros & Cons

Pros:

- One task boundary owns the low-effort policy.
- Shared chat and ingest effort behavior remains unchanged.
- No client mutation, wrapper, or provider-specific subclass is added.
- The UI catalogue and CLI command share exact model identifiers.

Cons:

- The extraction resolver repeats the small
  `latex_extract_model → vision_model → main` choice instead of delegating to
  the ingest resolver. This is intentional because the two tasks now have
  different effort policies.


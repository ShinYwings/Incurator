# Frontend And Security Proposal: Separate Activation, Discovery, And Inclusion
Date: 2026-07-26 | Agent Persona: Lead Architect

## 1. Core Logic & Implementation

Use three explicit boundaries instead of one overloaded state:

1. **Bundle activation:** the active plugin fingerprint must equal the installed
   bundle fingerprint before any provider starts.
2. **Tab discovery:** enumerate all eligible open leaves and preserve
   `isVisible`.
3. **Prompt inclusion:** visibility supplies the default, but the user's eye
   toggle/pin is the final per-session decision.

The Antigravity permission helper remains invocation-scoped and narrow. The
bundle activation guard guarantees that the helper currently on disk is
actually the helper running in memory.

## 2. Pros & Cons

### Pros

- Fixes the observed stale-hotfix failure at its lifecycle boundary.
- Makes chip count and open-tab discovery explainable.
- Avoids silently injecting all hidden files into every prompt.
- Preserves sandbox, no-ingest, and portable source-identity contracts.

### Cons

- Adds a small tri-state inclusion model rather than deleting one filter.
- Hidden PDF chips need an identity-only state before page capture completes.
- A one-time reload is still unavoidable for the currently running pre-hotfix
  bundle; no new code can execute inside code that has not been loaded.


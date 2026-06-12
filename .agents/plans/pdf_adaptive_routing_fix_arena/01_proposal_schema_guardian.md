# Schema Guardian Proposal: No False DB-Native Claims
Date: 2026-06-12 | Agent Persona: Schema Guardian

## 1. Core Logic & Implementation

Preserve the locked storage model:

- `state.sqlite` remains authoritative for source registration, L1 status,
  `source_spans` identity/provenance, and page metadata.
- CTX markdown remains a derived projection and may be regenerated.
- No migration is introduced in the v0.5.6 follow-up.
- API responses explicitly distinguish:
  - `durable_l1_projection`: served from registered CTX/source-span locators;
  - `ephemeral_parse`: read-only parse from original PDF.

Documentation must not claim that full CTX text is stored in SQLite. It must say
that L1 completion changes routing to registered durable L1 records/projection,
with original-source parse as a visible degradation fallback.

## 2. Pros & Cons

Pros:
- Avoids contradicting the canonical storage model.
- Makes fallback behavior observable.

Cons:
- The desired fully DB-native exact-section serving remains incomplete until a
  future schema explicitly stores full source-span text.

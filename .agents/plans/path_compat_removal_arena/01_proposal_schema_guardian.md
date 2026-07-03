# Schema Proposal: Preserve Current Schema, Drop Legacy Inputs
Date: 2026-07-04 | Agent Persona: schema_guardian

## 1. Core Logic & Implementation

Keep schema version 11 and the current `sources.external_ref` /
`sources.import_origin_ref` columns. Do not introduce another schema version:
the stored contract is unchanged. Remove only the v9 source-table converter.
Before code deployment, create a byte-for-byte DB backup, run the existing
normalizer, and verify `integrity_check`, `foreign_key_check`, source identities,
and absence of absolute source locators.

## 2. Pros & Cons

This avoids a fake schema bump for a code-path deletion and protects current
data. The rollout ordering is strict: normalizing after compatibility removal
would be impossible from the new CLI.

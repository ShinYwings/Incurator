# Schema Guardian Proposal: Versioned Diagnostic Evidence Contract

Date: 2026-06-11 | Agent Persona: schema_guardian

## 1. Core Logic & Implementation

Failure-atlas records and evidence bundles require versioned identities for case,
oracle, corpus, schema, config, model, request, selected evidence, and observed
result. Diagnostic state must remain separate from knowledge truth and cannot
silently mutate authoritative records.

## 2. Pros & Cons

Pros: makes baseline comparisons and handoffs reproducible. Cons: additional
identity/retention decisions are required before the observatory can persist
diagnostic artifacts safely.

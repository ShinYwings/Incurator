# Schema Guardian Proposal: No Research Spike Becomes Production State

Date: 2026-06-11 | Agent Persona: schema_guardian

## 1. Core Logic & Implementation

Spikes operate only on immutable exports or copied disposable databases. A
research decision may lock a future contract requirement, but cannot add a
production table, dependency, import path, or compatibility behavior. Every
schema implication is handed to the owning later plan for specs-first approval.

## 2. Pros & Cons

Pros: protects `state.sqlite` authority and makes research disposable. Cons:
copied-state behavior may not expose every production-scale issue, which must be
recorded as a limitation rather than hidden.

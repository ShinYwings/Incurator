# Schema Guardian Proposal: Reversible Resolution And Support Lifecycles

Date: 2026-06-11 | Agent Persona: schema_guardian

## 1. Core Logic & Implementation

Schema contracts must distinguish aliases, merge proposals/decisions/reversals,
relation support records, quarantined edges, hierarchy configuration identity,
and report dependencies. Accepted merges preserve origin and rewrite lineage;
no destructive overwrite is a valid resolution mechanism.

## 2. Pros & Cons

Pros: supports audit, reversal, and precise reconciliation. Cons: additive
lifecycle tables increase migration and operational complexity and require a
clean rebuild/rollback rehearsal.

# Pipeline Integrity Proposal: DB-Authoritative Status and Revisioned Sources

Date: 2026-07-03 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

Ship schema v11 with `sources.updated_at`, use it for JSONL LWW, and make all
dashboard density counts query the DB serving sets. Separate projection repair
from source validity. Fix emitted Zotero-key resolution and provide a safe
production reconciliation sequence: backup, peer import, DB projection re-emit,
then targeted L1 retry.

The deferred v0.30.1 sync-hardening items belong in the same release because
they affect the same transport: atomic snapshot/state writes, serialized profile
writes, read-merge-before-write profiles, MCP/worker export triggers, and
duplicate export elimination.

## 2. Pros & Cons

Pros: fixes the causal data model instead of one dashboard; restores convergence;
keeps DB authority explicit; provides a repair path that does not trust stale
Markdown.

Cons: requires a schema migration and broad mutation-path tests; production L4
data cannot be reconstructed from stale projections if no peer snapshot retains
the authoritative rows.

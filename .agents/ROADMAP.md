# Incurator Active Roadmap

Updated: 2026-07-31

This file contains only live work. Completed milestones and planning artifacts
belong in Git history, not the active workspace. New raw reports enter through
`.agents/USER_REPORT.md`.

## Active Queue

1. **v0.39.2 Equation-Reference PDF Context — implementation ready**
   - Fix latest-user references such as `수식 (10)` when the target lies just
     outside the already assembled PDF page text.
   - Preserve headless least privilege; resolve through the plugin's read-only
     PDF context boundary.
   - Plan: `.agents/plans/03_v0392_equation_reference_context.md`

2. **v0.39.x Stability Regression Audit — P6 through P10**
   - P6: durable sessions/secrets/config writes and runtime redaction.
   - P7: provider, MCP, cancellation, shutdown, timeout, and output bounds.
   - P8: vector degradation, provider cardinality, failover attribution, and
     prompt-version ordering.
   - P9: two dry passes across the v0.32.0–v0.39.x release chain.
   - P10: final validation and workflow closure.
   - Plan: `.agents/plans/02_v032_regression_audit.md`

3. **System Stability Overhaul — remaining umbrella scope**
   - Prompt v2 consistency harness and normalization.
   - Remaining safe god-file decomposition and broad-exception hardening.
   - Measured RAG/DAG performance work and existing-surface UX refinements.
   - Plan: `.agents/plans/01_system_stability_overhaul.md`

4. **Chat Session Context Compaction**
   - Draft: `.agents/drafts/chat_context_compaction.md`

5. **Vault Storage Governance & Quota Visibility**
   - Draft: `.agents/drafts/vault_storage_governance.md`

6. **Native PDF Annotation & Asset System**
   - Draft: `.agents/drafts/pdf_annotation_system.md`

7. **Web Search Integration**
   - No current plan. Re-plan from current provider, privacy, and cost
     constraints before implementation.

## Blocked / Icebox

- None.

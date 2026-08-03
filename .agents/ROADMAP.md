# Incurator Active Roadmap

Updated: 2026-08-01

This file contains only live work. Completed milestones and planning artifacts
belong in Git history, not the active workspace. New raw reports enter through
`.agents/USER_REPORT.md`.

## Active Queue

0. **[HOTFIX] PDF Cross-Reference Resolution & Context Retrieval (v0.40.3, in progress)**
   - RC1 theorem-family regex, RC2 printed→physical offset inference +
     fail-closed explicit pages, RC3 caption-index theorem family + appendix
     outline alias. Plugin-side only.
   - Plan: `.agents/plans/03_pdf_crossref_hotfix.md` (arena:
     `.agents/plans/hotfix_pdf_crossref_arena/`)
   - Deferred follow-up (Minor, needs own plan): agentic PDF retrieval tools
     for Ask AI/Sidechat (`fetch_pdf_page`, `search_pdf_anchor`).

1. **v0.40.x Stability Regression Audit — P7 through P10**
   - P7: v0.40.1 provider/MCP/process lifetime patch merged in PR #106.
   - P8: v0.40.2 vector degradation, provider cardinality, failover
     attribution, prompt-version ordering, and RF5-RF7 follow-up merged in PR #107.
   - P9: two dry passes across the v0.32.0–v0.39.x release chain.
   - P10: final validation and workflow closure.
   - Plan: `.agents/plans/02_v032_regression_audit.md`

2. **System Stability Overhaul — remaining umbrella scope**
   - Prompt v2 consistency harness and normalization.
   - Remaining safe god-file decomposition and broad-exception hardening.
   - Measured RAG/DAG performance work and existing-surface UX refinements.
   - Plan: `.agents/plans/01_system_stability_overhaul.md`

3. **Chat Session Context Compaction**
   - Draft: `.agents/drafts/chat_context_compaction.md`

4. **Vault Storage Governance & Quota Visibility**
   - Draft: `.agents/drafts/vault_storage_governance.md`

5. **Native PDF Annotation & Asset System**
   - Draft: `.agents/drafts/pdf_annotation_system.md`

6. **Web Search Integration**
   - No current plan. Re-plan from current provider, privacy, and cost
     constraints before implementation.

## Blocked / Icebox

- None.

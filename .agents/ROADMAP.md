# Incurator Active Roadmap

Updated: 2026-08-01

This file contains only live work. Completed milestones and planning artifacts
belong in Git history, not the active workspace. New raw reports enter through
`.agents/USER_REPORT.md`.

## Active Queue

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

7. **Agentic PDF Retrieval Tools for Ask AI/Sidechat**
   - Deferred from the v0.40.3 crossref hotfix (Minor scope, needs its own
     Arena plan): equip Ask AI and Sidechat LLM loops with explicit PDF tools
     (`fetch_pdf_page(page_number)`, `search_pdf_anchor(anchor_text)`) plus a
     multi-hop recovery loop, so the model autonomously fetches a missed
     cross-reference target instead of emitting a missing-context disclaimer,
     and free-form sidechat questions ("What is Result A4.1 on page 581?")
     trigger the same retrieval. Historical context: `git show` the deleted
     `.agents/plans/03_pdf_crossref_hotfix.md` and
     `.agents/plans/hotfix_pdf_crossref_arena/` on the v0.40.3 release branch.

## Blocked / Icebox

- None.

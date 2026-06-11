# Arena Consensus: Stabilization Guardrails

Date: 2026-06-11 | Agent Persona: system_synthesizer

## 1. Resolved Decisions

1. Retrieval evaluation and provenance correctness are Program 1 prerequisites,
   not cleanup after tuning.
2. Metrics are reported per query family with a frozen holdout set.
3. Structured source locators supplement, never replace, `source_span_ids`.
4. Block references resolve within a vault-relative file; duplicate/stale anchors
   degrade to a valid file link with a trace warning.
5. Formula recovery is selective and evidence-preserving. Low-confidence VLM
   output is stored/reported as uncertain and cannot silently overwrite source
   text.
6. Formula retention is centrality-aware to prevent bloated knowledge units.
7. Entity resolution defaults to aliases/proposals. Automatic merge requires
   strict compatible evidence and remains auditable.
8. Hierarchical community detection is deterministic and measured; connected
   components remains a degraded fallback.
9. Quota and storage governance are transferred intact to the separate
   `.agents/drafts/vault_storage_governance.md` milestone.
10. The technical-component split is superseded. Programs 1, 2, and 3 use
    separate branches/PRs/version bumps and stop gates.
11. Graph resolution/community construction belongs to compiler integrity.
12. Retrieval tuning belongs after the evidence compiler is trusted.
13. Quota UI and Convert-to-LaTeX provider settings are separate milestones.
14. Program 1 must produce an approved Failure Atlas, External Design Matrix,
    Evaluation Specification, and Target Architecture Specification before code.

## 2. Required Planning Artifacts

- Root-level umbrella synthesis:
  `../03_rag_knowledge_quality_stabilization.md`.
- Six independently debated component plans:
  `../A_rag_retrieval_provenance.md`,
  `../B_math_extraction_distillation.md`,
  `../C_graph_quality.md`,
  `../D_current_system_failure_atlas.md`,
  `../E_external_research_design_matrix.md`, and
  `../F_agent_context_service.md`.
- Each component plan must retain its own Arena folder with problem, proposals,
  critique, and consensus.
- A separate evidence ledger created immediately before Program 1 coding begins.

## 3. Vulnerabilities & Flaws Resolved

- Component-first sequencing invalidated earlier baselines.
- Quota/provider UI expanded the quality milestone without proving correctness.
- A single oversized plan hid independent rollback and approval boundaries.

## 4. Suggested Alternatives Adopted Or Rejected

- Adopted one umbrella plus six dedicated Arenas in three ordered batches.
- Rejected wholesale framework adoption and count-based completion.

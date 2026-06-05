# Phase 0: Philosophical Alignment — Senior Committee Baseline

**Target Files**: `README.md`, `docs/philosophy/ABOUT.md`

**Panel**: Alice (Architect), Diana (Docs), Grace (UX Designer)

---

## The Foundation of Incurator

Before analyzing the codebase and runtime logic in Phases A-I, the committee established a baseline by reviewing the core philosophy that governs the Incurator system. Any architectural divergence from these three tenets is classified as a systemic failure.

### 1. Dual-Track Structure: The Curator & The Artist

**Alice (Chief Architect)**:
"The system's most critical metaphor is the strict separation between the AI space and the Human space.
- **The Curator (AI Space)**: Lives in `.curator/state.sqlite`. It manages L1 (Contexts), L2 (Atoms), and L3 (Concepts) purely as high-speed database records. It is a machine-readable archive.
- **The Artist (Human Space)**: Lives in `02_Wiki/`. This is the permanent collection where only synthesized, curated L4 Exhibitions are output as Markdown files for human interaction.

**Verdict**: The current implementation violates this philosophy in Phase B and H. The legacy `qmd` search engine forces L1-L3 data into intermediate files just to be searchable. Moving to SQLite FTS5 (Phase H) and removing the filesystem dependency (Phase A) is not just a performance optimization; it is a **philosophical mandate** to restore the Dual-Track structure."

### 2. Specification-Driven Exhibition (Dynamic Lenses)

**Grace (UI/UX Designer)**:
"Generic RAG systems retrieve knowledge as-is. Incurator is supposed to stage a tailored Exhibition based on the Artist's preferences defined in `curate.yml`. This means L4 is not a static file, but a dynamic, context-aware lens.

**Verdict**: The documentation (Phase F) still references deprecated static Exhibition lifecycles (e.g., `wiki sync --backward`), and the CLI (Phase C) completely lost the `wiki curate` command. The system must fully embrace the 'Dynamic Lens' architecture where Exhibitions are assembled at query time, driven entirely by `curate.yml` specs, without polluting the Human Space with temporary static files."

### 3. Prior Knowledge Correction (Backpropagation)

**Diana (Documentation Specialist)**:
"When an Artist spots an error or derives a new insight, it shouldn't just be appended to a note. It must propagate backward to update the affected L2 Atoms and L3 Concepts. This mirrors deep-learning backpropagation.

**Verdict**: The infrastructure (Phase G) contains outdated tests for a deprecated version of this backpropagation. Furthermore, the core engine (Phase A) currently updates insight candidate statuses without an atomic transaction, and the security model (Phase C) lacks strict HITL (Human-In-The-Loop) enforcements to prevent agents from bypassing the Artist's approval. The `curator_propose_correction` workflow must be elevated to a first-class, strictly validated API."

---

## Alignment Matrix for Phase A-I

Every subsequent phase of this deep analysis is anchored to these three philosophical tenets:

| Philosophy Tenet | Addressed In | Required Action |
|---|---|---|
| **Dual-Track AI/Human Space** | Phase A, Phase B, Phase H | Migrate entirely to `state.sqlite` FTS5. Stop using `qmd` as a crutch for AI-space knowledge. |
| **Spec-Driven Exhibition** | Phase C, Phase F | Restore dynamic `curate` workflows. Clean up hallucination-inducing documentation about static syncs. |
| **Knowledge Backpropagation** | Phase E, Phase G, Phase I | Implement strict HITL state machines for `insight_candidates`. Ensure LLM resilience during graph updates. |

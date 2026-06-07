---
description: Research workflow for Gaussian Splatting geometry workspaces
---

# Research Pipeline

Use this workflow when answering research questions, reviewing equations, comparing papers, or proposing implementation experiments for the Gaussian Splatting Geometry Lab.

## 0. Context Loading
- Read `research_digest.md` first.
- Read `curate.yml` to confirm the active source scope.
- Search `.curator/` for relevant Atoms, Concepts, and Exhibitions before relying on loose memory.
- If `.curator/` has no useful result, inspect local `Concepts/`, `related_works.md`, `methodology.md`, and paper notes.

## 1. Inquiry And Search
- Restate the research question as a geometric or implementation claim.
- Prefer project-local evidence: paper notes, reference PDFs/assets, and curated nodes.
- Use external literature only after local evidence is exhausted or when the user explicitly requests a broader survey.

## 2. Verification
- Challenge the claim before accepting it.
- Check projection, covariance, rank, determinant, scale ambiguity, cheirality, and differentiability assumptions.
- Separate mathematical validity from engineering approximations such as low-pass filters, Taylor truncation, rasterization shortcuts, or CUDA-specific optimizations.
- When useful, activate skills such as `linear_algebra_verifier`, `symbolic_solver`, `code_theory_alignment`, or `cuda_taylor_analyzer`.

## 3. Knowledge Update
- Exploratory ideas go to `Research Notes/YYYY-MM-DD.md`.
- Accepted claims go to `methodology.md`.
- Literature positioning goes to `related_works.md`.
- Local concept summaries go under `Concepts/`.
- Do not edit `03_Notes/` without researcher approval.

## 4. Daily Logging
- At the end of a research session, add a concise entry to `Research Notes/YYYY-MM-DD.md`.
- Update `research_digest.md` only with durable research conclusions, not process chatter.

## 5. Promotion
- Promote a claim to `methodology.md` only when it has survived geometric verification and explicit researcher agreement.
- Keep speculation labeled as a working hypothesis.

## 6. Action Items
- Put experiments, derivations, paper-reading tasks, and unresolved citation work in `todo_list.md`.

## 7. Coding And Execution
- Place all verification scripts, plots, and derived artifacts in `Artifacts/`.
- Keep generated outputs connected to the claim they verify.

---
description: incurator research workflow
---

# Research Pipeline

Use this workflow for research, equation review, paper comparison, and
implementation experiments in `{{project_name}}`.

## 0. Context Loading

- Read `curate.yml` first.
- Use incurator MCP first when available, with `WORKSPACE_PATH={{workspace_path}}`.
- Start from L4 Exhibitions, then backtrack to Concepts, Atoms, and Contexts
  only when confidence or provenance requires it.
- If MCP and local Curator files are unavailable, say that no local fallback is
  available.

## 1. Verification

- Challenge claims before accepting them.
- Check projection, covariance, rank, determinant, scale ambiguity, cheirality,
  differentiability, and approximation assumptions when relevant.
- Separate verified claims, approximations, hypotheses, and unknowns.

## 2. Knowledge Update

- Record exploratory ideas in local research notes when the workspace uses them.
- Promote to `02_Wiki/` only after explicit human consensus.
- Use `wiki sync` after Curator corrections when practical.

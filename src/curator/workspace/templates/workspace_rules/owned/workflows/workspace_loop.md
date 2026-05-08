---
description: Incurator workspace loop
---

# Workspace Loop

Use this workflow when working inside `{{project_name}}`.

## 1. Load Scope

- Read `curate.yml`.
- Prefer Incurator MCP with `WORKSPACE_PATH={{workspace_path}}`.
- Start from Exhibitions, then backtrack only as needed.

## 2. Work With Evidence

- Separate sourced claims, hypotheses, and unknowns.
- Keep local drafts inside the workspace until the human accepts them.
- Do not invent citations or source paths.

## 3. Update The Graph

- Promote accepted knowledge to `02_Wiki/` only with explicit human consensus.
- After accepted changes, run or request `wiki add`, workspace curation, and `wiki sync` when practical.
- Leave ambiguous Curator repair items visible for review.


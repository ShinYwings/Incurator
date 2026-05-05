# Testbed Scenario

The repo-local `testbed/` vault is a development validation fixture generated
from `src/llm_wiki/templates/testbed_scenario/`.

`scripts/create_testbed.py --force` copies the checked-in scenario template
directly into `testbed/`, then performs the non-interactive equivalent of
`wiki init` to create `.obsidian/`, topology folders, `.curator/config.yml`,
`state.sqlite`, and empty Collection layer directories. Curator pages are not
seeded; validation must generate them through `wiki add`, `wiki curate`, and
related commands.

The generated `.curator/config.yml` intentionally uses Gemini CLI as the testbed
LLM backend (`llm.primary: gemini-cli`, `llm.gemini_flash_model:
gemini-3.1-flash-lite-preview`). LLM-sensitive validation requires the `gemini`
command to be installed and authenticated.

The source corpus under `02_Wiki/`, `03_Notes/`, `04_Resources/`, and
`05_Assets/` is immutable scenario input. Do not rewrite, sanitize, or simplify
those files during validation; update the template only when the user explicitly
changes the scenario corpus.

## Immutable Source Corpus

- `03_Notes/Papers/2D Gaussian Splatting for Geometrically Accurate Radiance Fields.md`
  is the human paper note for the 2D Gaussian Splatting reference.
- `04_Resources/Zotero/Huang et al. - 2024 - 2D Gaussian Splatting for Geometrically Accurate Radiance Fields.pdf`
  is the corresponding source reference.
- `03_Notes/Papers/EWA splatting.md` is the human paper note for EWA Splatting.
- `04_Resources/Zotero/Zwicker et al. - 2002 - EWA splatting.pdf` and related
  assets under `05_Assets/Zotero Assets/EWAsplatting_Zwicker2002/` are the
  corresponding reference material.
- `02_Wiki/LLM/rag-overview.md` is a deliberately separate knowledge-management
  topic.

## Expected Curator Behavior

- L1 Contexts preserve source provenance separately for each note and reference.
- L2-L4 should merge the 2DGS/EWA note-reference material into splatting
  geometry concepts where the claims support each other.
- RAG content should remain a distinct topic cluster, with only low-weight
  foundational overlap around retrieval, representation, and knowledge graphs.

## Workspace Scenario

The generated workspace is copied from
`src/llm_wiki/templates/testbed_scenario/01_Workspaces/Gaussian Splatting Geometry Lab/`.
Its `.agents/` and `.antigravity/` files describe the fictional research
project's working style only. They must not contain llm-wiki development
checklists, schema-auditor roles, or testbed validation instructions.

Repo-level testbed validation rules remain in `AGENTS.md`.

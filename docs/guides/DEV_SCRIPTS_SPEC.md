# Guide: Creating Development Testbed Scenarios

This guide explains how to create and manage development validation scenarios (testbeds) to verify Incurator's behavior in isolated environments.

## 1. Scenario Structure
Every scenario lives in `scripts/dev/<scenario_name>/`. Use the `testbed_template` as your starting point.

```text
scripts/dev/<scenario_name>/
├── MASTER_PLAN.md          # [Required] Goals and setup instructions
├── stage/                  # [Required] The raw source files (L0)
│   ├── 01_Workspaces/      # Workspace definitions (curate.yml)
│   ├── 03_Notes/           # Sample markdown notes
│   └── 04_Resources/       # Sample reference PDFs/HTML
├── dialogues/              # [Optional] Automation scripts (.sh or .py)
├── fixture_workspace_rules/ # [Optional] Agent rules for this scenario
└── create_testbed.py       # [Legacy] Optional custom setup script
```

## 2. Step-by-Step Creation

### Step 1: Initialize the Folder
Copy `scripts/dev/testbed_template` to `scripts/dev/my_scenario`.

### Step 2: Define the Master Plan (`MASTER_PLAN.md`)
This document is the identity of your scenario. It must describe:
- **Scenario Name**: Clear title.
- **Problem Statement**: What bug or feature are you testing?
- **Validation Goals**: What are the success criteria? (e.g., "Atom ATM-123 must contain the specific logic derivation").

### Step 3: Seed the Stage (`stage/`)
Place the minimum set of files required to reproduce the behavior in `stage/`.
- Use **anonymized** data. Never commit private notes.
- Ensure at least one workspace exists in `01_Workspaces/` if you are testing `wiki curate`.

### Step 4: Write Automation Dialogues (`dialogues/`)
Dialogues automate the verification. 
- Create `dialogues/verify_fix.sh`.
- Use `VAULT_ROOT=testbed` for all commands.
- **Example**:
  ```bash
  # 1. Reset and Init
  wiki testbed init my_scenario --force
  
  # 2. Run Pipeline
  VAULT_ROOT=testbed wiki add "03_Notes/bug_report.md"
  VAULT_ROOT=testbed wiki sync
  
  # 3. Assert
  if grep -q "Expected Insight" testbed/.curator/Collections/02_Atoms/*.md; then
    echo "✓ Success"
  else
    echo "✗ Failed"
    exit 1
  fi
  ```

## 3. Execution Workflow
1. **Discovery**: Run `wiki testbed list` to see your new scenario.
2. **Initialization**: Run `wiki testbed init <name> --force`.
3. **Execution**: Run your dialogue script manually: `bash scripts/dev/<name>/dialogues/verify_fix.sh`.

## 4. Best Practices
- **Minimize State**: Only include the files strictly necessary for the test.
- **Doc-First**: The `MASTER_PLAN.md` should be clear enough for another developer to understand the test without reading the code.
- **Clean Up**: If your test creates temporary files outside of `testbed/`, clean them up in the dialogue script.

## 5. Plugin Development & Monorepo Build (v0.2.0)

Incurator v0.2.0 uses a Monorepo structure containing both the Python backend (`backend/`) and the Obsidian plugin (`plugin/`).

During transition, some checkouts may still keep the backend at repository root (`src/`, `tests/`, `pyproject.toml`) and the active plugin inside an Obsidian vault path such as `.obsidian/plugins/incurator-obsidian-agent`. Development scripts must not assume the target layout has already landed. When a script depends on a path depth, record the evidence in `docs/plans/INCURATOR_SYSTEM_BUILD_EVIDENCE.md` and update the master plan before changing code.

### Setup Script
Run `./setup.sh` at the repository root to automatically install the Python backend dependencies (via `uv`), install Node.js dependencies, and build the Obsidian plugin.

### OBSIDIAN_PLUGIN_DIR Override
To develop the Obsidian plugin locally without manually copying files or creating brittle symlinks, you can use the `OBSIDIAN_PLUGIN_DIR` environment variable.
When `OBSIDIAN_PLUGIN_DIR` is set (e.g., `export OBSIDIAN_PLUGIN_DIR=/path/to/second_brain/.obsidian/plugins/incurator-plugin`), the plugin's `esbuild.config.mjs` will dynamically override the build output directory (outdir).
This allows you to run `npm run dev` in the `plugin/` directory and have changes immediately reflected in your active Obsidian vault.

### Evidence-First Path Migration

Path migrations are high-risk because the backend discovers vault roots, testbed roots, bundled assets, and plugin output paths by walking parent directories. Before changing any `parents[N]`, relative path, or build output location:

1. Record the current path, expected new path, and command that proves the assumption.
2. Update the master build plan if the change affects backend/plugin boundaries.
3. Run the smallest command that exercises the changed path.
4. Run the relevant full check when available.

For example, a backend move from root `src/` to `backend/src/` must be accompanied by checks for:

- `wiki testbed init testbed_template --force`
- `VAULT_ROOT=<testbed> wiki status`
- parser fixture paths
- MCP launch path
- plugin build output path

### External Resource Testbeds

Reference Mode and copy import require explicit fixtures:

- one copied PDF fixture under `stage/04_Resources/`
- one external PDF fixture outside the generated testbed root
- one same-name/different-hash collision case
- one moved-file or rebind proposal case
- one page-provenance assertion that verifies `curator_search_source` or `curator_get_pdf_page`

Do not commit private Zotero libraries or personal PDFs. Use minimal public-domain PDFs or synthetic text PDFs for public fixtures.

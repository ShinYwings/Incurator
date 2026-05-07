# Specification: Development Testbed Framework

This document defines the standard for creating and managing development validation environments (testbeds) in the InCurator project.

## 1. Directory Structure
All testbed scenarios must be located under `scripts/dev/` and follow this structure:

```text
scripts/dev/<scenario_name>/
├── create_testbed.py       # Setup script
├── MASTER_PLAN.md          # Scenario documentation
├── stage/                  # Source corpus (Notes, Resources, etc.)
│   └── 01_Workspaces/      # Workspace files
│   └── 03_Notes/           # Sample human notes
│   └── 04_Resources/       # External reference files
├── fixture_workspace_rules/ # Custom agent rules for the testbed
└── dialogues/              # Action scripts for automated testing
```

## 2. The Setup Script (`create_testbed.py`)
The setup script is responsible for:
1. **Root Preparation**: Cleaning the project-root `testbed/` directory.
2. **Seeding**: Copying the `stage/` fixture into `testbed/`.
3. **Initialization**: Running a non-interactive `wiki init` equivalent (creating `.curator/`, DB, config).
4. **Provisioning**: Installing agent rules from `fixture_workspace_rules/` into the testbed workspaces.

## 3. Workflow
To develop or validate a feature:
1. **Choose/Create Scenario**: Use an existing folder in `scripts/dev/` or copy `testbed_template/`.
2. **Initialize**: Run `python scripts/dev/<scenario_name>/create_testbed.py --force`.
3. **Verify**: Use `WIKI_ROOT=testbed wiki ...` commands to perform validation as described in the scenario's `MASTER_PLAN.md`.

## 4. Best Practices
- **Isolation**: Never modify files in `03_Notes/` or `04_Resources/` within the testbed assets; they are immutable inputs.
- **Reproducibility**: Ensure the `create_testbed.py` script makes the environment identical every time it runs with `--force`.
- **Sanitization**: Remove all personal information (names, private paths, actual internal notes) from testbed assets before committing.

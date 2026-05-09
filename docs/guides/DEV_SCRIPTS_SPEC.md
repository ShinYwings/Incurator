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

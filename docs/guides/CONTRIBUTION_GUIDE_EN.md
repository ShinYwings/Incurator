# Contribution Guide

## 1. Project Overview
InCurator is an LLM-maintained personal knowledge base (Zettelkasten) integrated with Obsidian. It builds a verifiable knowledge graph through a 4-layer curation pipeline.

## 2. Core Development Principles
- **Simplicity**: Minimum code to solve the problem.
- **Surgical Changes**: Touch only what you must.
- **Testbed-Driven**: All changes must be verified in the testbed.

## 3. Development Environment: Testbed Pattern
The Testbed is an independent, reproducible environment used to verify system behavior without affecting the actual vault.

### 📂 Testbed Asset Management
For a detailed technical guide on creating, managing, and automating testbed environments, please refer to the [Development Testbed Framework Specification](file:///home/shin/Workspace/llm_wiki/docs/guides/DEV_SCRIPTS_SPEC.md).

### 🔄 Working with Scenarios
1. **List Scenarios**: Run `wiki testbed list` to see available validation sets.
2. **Initialize**: Run `wiki testbed init <scenario_name> --force` to set up the `testbed/` vault.
3. **Verify**: Perform your changes and run the validation steps outlined in the scenario's `MASTER_PLAN.md`.

## 4. Submission Checklist
- [ ] Run `ruff check src/` and `mypy src/`.
- [ ] Run `pytest`.
- [ ] Verify changes in the `testbed/` vault using `wiki testbed init <scenario> --force`.
- [ ] Ensure `AGENTS.md` and `GEMINI.md` are synchronized.

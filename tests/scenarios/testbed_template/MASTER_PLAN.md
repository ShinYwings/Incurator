# Testbed Scenario Template

This is the domain-neutral template for creating development validation scenarios.
Copy this directory to `tests/scenarios/<your_scenario_name>/` as a starting point.

## Overview

This testbed simulates a clean knowledge integration environment. It is used to verify
core Curator behaviors — L1-L4 pipeline, DAG integrity, DB-native search — without
domain-specific noise.

## Setup

```bash
wiki testbed init testbed_template --force
VAULT_ROOT=testbed wiki status
```

## Asset Roles

- `stage/`: The source corpus and workspace files seeded into `testbed/`.
- `mock_zotero_env/`: Optional mock Zotero data directory for reference-mode tests.
- `dialogues/`: Optional automation scripts for validation.

## Validation Goals

### G1: L1 Extraction

- `wiki add` correctly parses documents in `stage/03_Notes/` and `stage/04_Resources/`.
- Each source produces a distinct CTX-* node in `.curator/Collections/01_Contexts/`.

### G2: L2 Atoms

- `wiki add` (Phase A) extracts atomic facts from each L1 Context.
- ATM-* nodes appear in `.curator/Collections/02_Atoms/`.

### G3: L3 Concepts

- Cross-document concept clustering produces CON-* nodes.
- `.curator/Collections/03_Concepts/` is non-empty after pipeline.

### G4: L4 Synthesis

- Shared synthesis produces SYN-* nodes in `.curator/Collections/04_Synthesis/`.

### G5: DB-Native Search

- `wiki query "sample"` returns results backed by SQLite FTS5/BM25 index.
- No external `qmd` binary is required.

### G6: DAG Integrity

- `wiki sync` runs without errors.
- `wiki lint` reports no broken wikilinks or orphan nodes.

### G7: Zotero Reference Mode

- `mock_zotero_env/storage/TESTKEY1/mock_paper.pdf` is accessible via reference mode.
- `zotero://open-pdf/library/items/TESTKEY1` resolves to the mock PDF path.

## Creating a New Scenario

1. Copy this directory: `cp -r tests/scenarios/testbed_template tests/scenarios/my_scenario`
2. Edit `MASTER_PLAN.md` to describe your problem and success criteria.
3. Replace or augment `stage/` with your test corpus.
4. Add `stage/01_Workspaces/<Name>/curate.yml` if testing workspace queries.
5. Write `dialogues/verify_fix.sh` to automate assertions.
6. Run `wiki testbed init my_scenario --force` to initialize.

Custom scenarios are automatically excluded from git (see `.gitignore`).
Only `testbed_template` itself is tracked.

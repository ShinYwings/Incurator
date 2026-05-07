# Testbed Master Plan: Generic Template

This is a domain-neutral template for creating development validation scenarios.

## Overview
This testbed simulates a clean knowledge integration environment. It is used to verify core curator behaviors (L1-L4 pipeline, DAG integrity, and search) without domain-specific noise.

## Setup
Run the following command to initialize the testbed:
`python scripts/dev/testbed_template/create_testbed.py --force`

## Asset Roles
- `stage/`: The source corpus and workspace files.
- `fixture_workspace_rules/`: Custom agent rules for the testbed.
- `dialogues/`: Scripts for automated interaction testing.

## Validation Goals
1. **L1 Extraction**: Verify `wiki add` correctly parses documents in `stage/`.
2. **Phase A (Atoms)**: Verify `wiki curate` extracts atomic facts.
3. **Phase B (Concepts)**: Verify cross-document clustering.
4. **Phase C (Exhibitions)**: Verify synthesis of final exhibition nodes.
5. **Search**: Verify QMD indexing and query synthesis.

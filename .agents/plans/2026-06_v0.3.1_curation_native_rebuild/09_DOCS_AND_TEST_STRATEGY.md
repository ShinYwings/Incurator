# Docs And Test Strategy For v0.3.1

## 1. Purpose

This document defines how v0.3.1 planning becomes source-of-truth docs and how
future implementation will be validated.

The current phase writes plans only. The next phase must update docs/specs
before code implementation.

## 2. Spec Update Order

Create synchronized v0.3.1 specs:

```text
docs/specs/curator_schema/SCHEMA_v0.3.1.md
docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.3.1.md
docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.3.1.md
```

Move current root v0.2.2 specs into:

```text
docs/specs/curator_schema/archives/
docs/specs/system_behavior/archives/
docs/specs/plugin_schema/archives/
```

Root of each spec domain should contain only the active v0.3.1 file.

## 3. Guide Update Order

Update English guides first:

- `docs/guides/USER_GUIDE.md`
- `docs/guides/WORKFLOW_GUIDE.md`
- `docs/guides/MCP_USER_GUIDE.md`
- `docs/guides/PLUGIN_GUIDE.md`

Then update faithful Korean translations:

- `docs/guides/USER_GUIDE_KR.md`
- `docs/guides/WORKFLOW_GUIDE_KR.md`
- `docs/guides/MCP_USER_GUIDE_KR.md`
- `docs/guides/PLUGIN_GUIDE_KR.md`

Do not use Korean guides as the canonical source for new behavior.

## 4. Philosophy Docs

Update if v0.3.1 reframes the product:

- `docs/philosophy/ABOUT.md`
- `docs/philosophy/ABOUT_KR.md`

The philosophy update should emphasize:

- `curate.yml` as Knowledge Requirement Specification;
- Curator as curation compiler;
- Artist as workspace agent/human;
- Exhibition as staged context;
- backprop as feedback loop;
- prompt contracts as part of trust.

## 5. Required Spec Topics

### 5.1 Curator Schema

Define:

- upgraded L1 source map fields;
- typed L2 knowledge units;
- entities;
- relations;
- source spans;
- community reports;
- memory paths;
- prompt runs;
- curation plans;
- insight candidates;
- backprop events.

### 5.2 System Behavior

Define:

- `curate.yml` KRS lifecycle;
- curation plan flow;
- local/global/explore/exhibition routing;
- prompt registry behavior;
- prompt trace requirements;
- backprop classification;
- source truth protection;
- promotion lifecycle.

### 5.3 Plugin Schema

Define:

- local JSON command payloads;
- trace panel payloads;
- prompt trace rendering data;
- insight candidate actions;
- version compatibility behavior.

## 6. Backend Test Strategy

Future backend pytest coverage:

- `curate.yml` parser accepts current and v0.3.1 shapes.
- curation plan generation respects source include/exclude.
- prompt registry has unique prompt ids.
- prompt contracts declare validators.
- prompt trace records id/version/model/hash.
- source map preserves markdown/PDF/math spans.
- knowledge-unit extraction requires source spans.
- entity/relation extraction rejects invented source ids.
- community report generation includes representative evidence.
- query router selects local/global/explore/exhibition.
- backprop diagnosis distinguishes correction, contradiction, derived insight,
  style-only edit, and promotion.
- promotion writes only to `02_Wiki/`.

The exact code-level test file names and patch sequencing are specified in
`11_CODE_LEVEL_IMPLEMENTATION_BLUEPRINT.md`. Treat that document as the
implementation checklist after v0.3.1 specs are approved.

## 7. Plugin Test Strategy

Future Vitest coverage:

- plugin system prompt gives correct external MCP guidance;
- plugin calls local JSON commands for same-device curation flows;
- trace panel renders:
  - route;
  - source spans;
  - prompt id/version;
  - community reports;
  - insight candidates;
- promotion button calls correct backend command;
- workspace outside a `curate.yml` does not bind arbitrary workspace.

## 8. Prompt Eval Strategy

Prompt evals should be treated as tests.

Minimum fixtures:

- valid extraction with source spans;
- invalid extraction with invented ids;
- equation preservation;
- Korean/English language bridge;
- GraphRAG community report;
- global map/reduce output;
- DRIFT follow-up tree;
- derived insight vs source truth;
- contradiction detection;
- backprop patch plan;
- `curate.yml` false-merge warning.

## 9. Testbed Strategy

Default scenario:

```text
scripts/dev/complex_math_backprop
```

Future smoke commands:

```bash
wiki testbed init complex_math_backprop --force
VAULT_ROOT=testbed wiki status
VAULT_ROOT=testbed wiki add
VAULT_ROOT=testbed wiki build --wait
VAULT_ROOT=testbed wiki curate plan --workspace testbed/01_Workspaces/ResNet_Dynamics_Lab --json
VAULT_ROOT=testbed wiki curate --workspace testbed/01_Workspaces/ResNet_Dynamics_Lab
VAULT_ROOT=testbed wiki query "What is the dynamics interpretation of residual learning?" --workspace testbed/01_Workspaces/ResNet_Dynamics_Lab --mode explore
VAULT_ROOT=testbed wiki sync --backward --target EXH-...
VAULT_ROOT=testbed wiki lint
```

If qmd or LLM is unavailable:

- document exact blocker;
- run deterministic tests;
- run prompt validators;
- run simulated local_slm validation;
- do not call the full scenario passed.

## 10. Documentation Acceptance Criteria

Docs are ready when:

- v0.3.1 specs are synchronized across all spec domains;
- guides are updated in English and Korean;
- philosophy docs reflect the curation-native rebuild if needed;
- old v0.2.2 specs are archived;
- implementation plans reference v0.3.1 specs, not old root specs;
- docs preserve detail and do not compress prior architecture.

## 11. Implementation Acceptance Criteria

Future implementation is complete only when:

- backend tests pass;
- plugin tests pass;
- prompt evals pass or blockers are documented;
- testbed smoke passes or blockers are documented;
- docs and specs match implemented behavior;
- no code path allows source truth pollution;
- plugin does not directly mutate backend state;
- external MCP and plugin JSON contracts return compatible trace payloads.

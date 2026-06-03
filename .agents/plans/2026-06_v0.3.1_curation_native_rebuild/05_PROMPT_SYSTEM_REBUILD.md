# Prompt System Rebuild Plan

## 1. Purpose

This is the most important technical plan in the v0.3.1 suite.

Incurator's prompt system is currently powerful but too scattered. v0.3.1 should
turn prompts into a versioned, testable, traceable, contract-driven subsystem.

The goal is not prettier prompt text. The goal is to make prompt behavior part
of the architecture contract.

For code-level migration details, use this document together with
`11_CODE_LEVEL_IMPLEMENTATION_BLUEPRINT.md` sections 4 and 9. This prompt plan
defines the prompt architecture; the blueprint names the concrete package
layout, wrapper strategy, registry classes, trace dataclasses, validators, CLI
commands, and test files.

## 2. Current Prompt Problems

### 2.1 Scattered Ownership

Prompt behavior currently appears in:

- `backend/src/curator/prompts.py`
- `backend/src/curator/query.py`
- `backend/src/curator/lint.py`
- `backend/src/curator/workspace/provisioner.py`
- `plugin/src/context/systemPrompt.ts`
- backprop-related plans and utilities.

This makes it hard to reason about which prompt controls which behavior.

### 2.2 Missing Prompt Versioning

Generated artifacts generally do not record:

- prompt id;
- prompt version;
- prompt input hash;
- prompt output hash;
- model provider;
- model name;
- retry count;
- validator result.

Without these fields, prompt regressions are hard to diagnose.

### 2.3 Weak Output Contracts

Some prompts ask for JSON or Markdown, but output schema is not consistently
represented as code-level contracts with validators. Retries exist in some
paths, but prompt self-correction is not standardized.

### 2.4 Role Leakage

Curator, Artist, Verifier, Query Synthesizer, Extractor, and Backprop Diagnoser
roles blur together. A prompt that extracts source truth should not behave like
a prompt that synthesizes workspace insight.

### 2.5 `curate.yml` Underuse

`curate.yml` currently affects retrieval and persona context, but it should
shape prompt selection and prompt content much more directly:

- audience;
- output format;
- verification style;
- contradiction policy;
- exploration depth;
- prompt profile;
- source exclusions;
- backprop policy.

### 2.6 Evaluation Gap

Existing tests often assert that prompt strings include certain phrases. v0.3.1
needs prompt evals that validate behavior:

- no invented IDs;
- source-span preservation;
- output schema validity;
- language behavior;
- contradiction classification;
- source truth vs derived insight separation.

## 3. New Prompt Package

Add a future backend package:

```text
backend/src/curator/prompting/
├── __init__.py
├── registry.py
├── contracts.py
├── builder.py
├── validators.py
├── examples.py
├── trace.py
├── evals.py
└── families/
    ├── source_map.py
    ├── knowledge_units.py
    ├── entity_relation.py
    ├── community_report.py
    ├── curation_plan.py
    ├── exhibition.py
    ├── query.py
    ├── explore.py
    ├── backprop.py
    └── note_writing.py
```

This is a planning target, not implementation in this phase.

## 4. Prompt Registry

Every prompt should be registered with:

- `prompt_id`
- `version`
- `family`
- `role`
- `purpose`
- `input_contract`
- `output_contract`
- `validator`
- `retry_policy`
- `default_model_class`
- `supports_json_mode`
- `requires_source_spans`
- `allowed_temperature`
- `few_shot_examples`

Example prompt ids:

- `curator.source_map.v1`
- `curator.knowledge_unit_extract.v1`
- `curator.entity_relation_extract.v1`
- `curator.community_report.v1`
- `curator.curation_plan.v1`
- `curator.exhibition_outline.v1`
- `curator.exhibition_write.v1`
- `curator.query_router.v1`
- `curator.local_answer.v1`
- `curator.global_map.v1`
- `curator.global_reduce.v1`
- `curator.drift_primer.v1`
- `curator.drift_followup.v1`
- `curator.insight_candidate.v1`
- `curator.backprop_diagnose.v1`
- `curator.backprop_patch_plan.v1`
- `artist.note_context_pack.v1`
- `artist.note_edit_plan.v1`

## 5. Prompt Contract Shape

Each prompt contract should define:

```text
PromptContract
  id
  version
  role
  purpose
  required_inputs
  optional_inputs
  output_schema
  forbidden_outputs
  citation_rules
  confidence_rules
  source_truth_rules
  retry_policy
  validators
  trace_fields
```

## 6. Required Prompt Families

### 6.1 Source Map Prompt

Purpose:

- Convert source content into a structure-preserving source map.
- Preserve headings, page spans, math blocks, figures, and references.

Rules:

- Do not synthesize new insight.
- Do not translate source truth into a different claim.
- Preserve exact source spans where possible.
- Record uncertainty when parsing is ambiguous.

Output:

- source title;
- sections;
- spans;
- key source-local claims;
- math blocks;
- figure/table references;
- parse warnings.

### 6.2 Knowledge Unit Extraction Prompt

Purpose:

- Extract typed L2 units from source spans.

Unit types:

- claim;
- equation;
- definition;
- method;
- result;
- observation;
- constraint;
- entity;
- relation candidate.

Rules:

- Every unit must cite a source span.
- No span, no unit.
- If a statement is a derived interpretation, mark it as derived and do not
  attach it as source-authored.

### 6.3 Entity/Relation Extraction Prompt

Purpose:

- Build graph structure from knowledge units.

Rules:

- Use typed relations.
- Keep relation confidence.
- Distinguish "source states", "system infers", and "workspace derives".

### 6.4 Community Report Prompt

Purpose:

- Summarize a graph community for global reasoning.

Rules:

- Reports are generated retrieval aids, not human truth.
- Include representative claims and source spans.
- Include contradictions and unresolved gaps.
- Include "not enough evidence" where appropriate.

### 6.5 Curation Plan Prompt

Purpose:

- Convert `curate.yml` and graph status into a workspace curation plan.

Inputs:

- `curate.yml`;
- Curator persona;
- Artist persona;
- source inventory;
- concept/community inventory;
- active Exhibition metadata.

Output:

- source scope;
- retrieval modes;
- required evidence;
- excluded topics;
- output format;
- verification strategy;
- prompt profile;
- open gaps.

### 6.6 Exhibition Prompt

Purpose:

- Write or refresh an Exhibition as a workspace context package.

Rules:

- Use `curate.yml` as the controlling spec.
- Do not answer as a generic chatbot.
- Include evidence, implications, gaps, and agent directives.
- Separate source-backed claims from derived suggestions.
- Record backprop targets.

### 6.7 Query Router Prompt

Purpose:

- Choose local/global/explore/exhibition/source-section route.

Prefer deterministic routing first. Use LLM router only when deterministic
signals are uncertain.

Output:

- selected route;
- reason;
- confidence;
- needed context;
- fallback route.

### 6.8 Local Answer Prompt

Purpose:

- Answer precise questions from source spans, entities, claims, and concepts.

Rules:

- Prefer exact source spans.
- Cite claims.
- Avoid broad summary when the question is local.

### 6.9 Global Synthesis Prompt

Purpose:

- Use community reports and map/reduce intermediate points for broad questions.

Rules:

- Rated intermediate points must be traceable.
- Final answer must include report ids and source span backfill.

### 6.10 Explore Prompt

Purpose:

- Produce DRIFT-like exploratory paths.

Output:

- primer;
- follow-up questions;
- local refinements;
- insight candidates;
- confidence;
- "needs human review" flags.

### 6.11 Backprop Prompt

Purpose:

- Diagnose changes and plan safe repairs.

Classifications:

- correction;
- contradiction;
- new derived insight;
- style-only edit;
- unsupported claim;
- promotion request.

Rules:

- Never rewrite original source truth to include later derived insight.
- Propose generated-node patch targets only.
- Require human review for ambiguous merges.

### 6.12 Note-Writing Context Prompt

Purpose:

- Package Curator knowledge for the Artist writing in Obsidian.

Rules:

- Do not overwrite notes.
- Provide edit suggestions or `ai-agent-edit` blocks only when asked.
- Keep citations and provenance visible.

## 7. Prompt Trace

Every prompt run should record:

- trace id;
- prompt id;
- prompt version;
- operation id;
- workspace path;
- `curate.yml` hash;
- input hash;
- output hash;
- source ids;
- model provider;
- model name;
- effort/reasoning setting if applicable;
- temperature;
- latency;
- token counts when available;
- retry count;
- validator result;
- error if failed.

Prompt trace should be inspectable through:

- CLI;
- MCP;
- plugin trace panel.

## 8. Prompt Validators

Validators should check:

- valid JSON when schema expects JSON;
- required fields present;
- real Curator IDs only;
- no invented wikilinks;
- source span exists;
- confidence in range;
- no persisted language fields where prohibited;
- source truth vs derived insight distinction;
- no direct `03_Notes` mutation instructions;
- math delimiter compatibility for Obsidian.

## 9. Prompt Eval Strategy

Prompt eval fixtures should include:

- source claim extraction from a short paper section;
- equation preservation;
- Korean/English language bridge behavior;
- contradiction classification;
- later insight not backfilled into original source;
- `curate.yml` source exclusion;
- GraphRAG-style community report with source spans;
- DRIFT exploration with follow-up tree;
- invalid JSON self-correction.

## 10. Migration Strategy

Do not rewrite all prompts in one patch.

Recommended order:

1. Add registry/contracts/traces with no behavior change.
2. Move query router and curation plan prompts first.
3. Move Exhibition prompts.
4. Move extraction prompts.
5. Move backprop prompts.
6. Move plugin system prompt integration guidance.
7. Add eval tests after each family migration.

Code-level migration rule:

- `backend/src/curator/prompts.py` remains import-compatible at first.
- New prompt families live under `backend/src/curator/prompting/families/`.
- Existing functions such as `build_summary_messages()` and
  `build_curation_page_messages()` become wrappers that delegate to registered
  prompt contracts.
- `backend/src/curator/query.py` must stop owning `SYNTHESIS_SYSTEM_PROMPT`;
  that prompt moves to `prompting/families/query.py`.
- Pydantic output models that currently live in `ingest_llm.py` should either
  move to shared model modules or be explicitly imported by prompt contracts.
- Every migrated prompt must produce or update a `prompt_runs` trace row.

## 11. Acceptance Criteria

The prompt rebuild is ready for implementation when:

- every prompt family has a named contract;
- each contract defines inputs, outputs, validators, and trace fields;
- `curate.yml` influence is explicit;
- backprop prompts preserve source truth;
- prompt eval fixtures are specified;
- generated artifacts can record prompt provenance.

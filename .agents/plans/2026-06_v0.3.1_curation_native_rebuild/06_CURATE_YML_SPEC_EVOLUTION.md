# curate.yml Spec Evolution Plan

## 1. Purpose

`curate.yml` is Incurator's Knowledge Requirement Specification. v0.3.1 should
make that true in schema, prompts, CLI behavior, MCP tools, and plugin UI.

Currently, `curate.yml` contains project metadata, source include/exclude,
persona fields, confidence thresholds, topics, and active Exhibition references.
This is useful, but it does not yet drive the full curation compiler.

## 2. Design Goal

`curate.yml` should define what the Artist needs from the Curator:

- what knowledge matters;
- which sources are allowed;
- which sources are excluded;
- what output should look like;
- how evidence should be verified;
- how contradictions should be handled;
- when exploration should happen;
- what prompt profile should be used;
- how backprop should treat corrections and new insights.

## 3. v0.3.1 Conceptual Shape

Suggested high-level sections:

```yaml
project: "resnet-dynamics-lab"
description: "Workspace purpose."
vault_root: "/path/to/vault"

goal:
  primary: "Explain and extend residual-network knowledge through a dynamics lens."
  audience: "researcher"
  deliverables:
    - "curated-exhibition"
    - "research-note-context"
  success_criteria:
    - "Every mathematical claim cites a source span."
    - "Later Neural ODE insight is separated from original ResNet source truth."

sources:
  include:
    - "03_Notes/**"
    - "04_Resources/**"
  exclude:
    - "03_Notes/private/**"
  reference_mode:
    allow_external: true
    require_rebind_approval: true

knowledge:
  domains:
    - "machine-learning"
    - "computer-vision"
    - "dynamical-systems"
  topics:
    - "residual learning"
    - "degradation problem"
    - "Euler discretization"
  disambiguation_keywords:
    - "ResNet"
    - "Neural ODE"
  avoid_merges:
    - "original ResNet claim != later ODE interpretation"

output:
  format: "exhibition"
  style: "dense-technical"
  citation_style: "curator-source-spans"
  include_sections:
    - "Evidence Map"
    - "Conceptual Synthesis"
    - "Unresolved Gaps"
    - "Agent Directives"

reasoning:
  modes:
    default: "auto"
    allow:
      - "local"
      - "global"
      - "explore"
      - "exhibition"
  exploration:
    enabled: true
    max_followups: 5
    require_insight_candidates: true

verification:
  min_confidence: 0.70
  high_threshold: 0.85
  require_source_spans: true
  allow_general_knowledge: false
  contradiction_policy: "surface-and-flag"

backprop:
  enabled: true
  source_truth_policy: "never_rewrite_original_source"
  derived_insight_policy: "record_then_promote_or_patch_generated"
  ambiguous_merge_policy: "needs_review"

prompts:
  profile: "technical-research"
  output_language: "same_as_latest_request"
  prompt_overrides: {}
```

This is a planning shape, not a finalized schema.

## 4. Required Semantic Changes

### 4.1 Goal

The goal section should tell the Curator why the workspace exists and what a
successful Exhibition should enable. It should not be only a description string.

### 4.2 Audience

Audience affects prompt style and output density:

- researcher;
- engineer;
- learner;
- writer;
- generalist.

The same source graph can produce very different Exhibitions depending on
audience.

### 4.3 Source Policy

Source policy must include:

- include/exclude globs;
- Reference Mode allowance;
- private/source exclusions;
- whether promoted `02_Wiki` pages are allowed as sources;
- how to treat moved or hash-drifted external sources.

### 4.4 Knowledge Scope

Knowledge scope should include:

- domains;
- topics;
- entity hints;
- disambiguation keywords;
- explicit false-merge warnings;
- desired bridge concepts.

False-merge warnings are important for cases like:

```text
Original ResNet paper claims != later Neural ODE interpretation
```

### 4.5 Output Contract

The output section should control:

- artifact type;
- required sections;
- citation style;
- density;
- whether to include open questions;
- whether to include agent directives;
- whether to include insight candidates.

### 4.6 Reasoning And Retrieval Modes

The spec should tell the Curator whether exploration is allowed or desired.
Some workspaces want exact grounded answers. Others want broad discovery.

### 4.7 Verification

Verification policy should become explicit:

- source spans required or optional;
- confidence thresholds;
- whether general knowledge is allowed;
- contradiction handling;
- unsupported-claim behavior.

### 4.8 Backprop

Backprop policy should tell the Curator what to do with feedback:

- generated-node correction;
- new derived insight;
- promotion candidate;
- contradiction requiring review;
- style-only update.

## 5. Prompt Integration

`curate.yml` should be compiled into prompt inputs, not pasted as vague context.

Every curation prompt should receive structured fields:

- source policy;
- goal;
- audience;
- output contract;
- verification policy;
- backprop policy;
- prompt profile.

Prompt validators should confirm the output respects those fields.

## 6. CLI And MCP Implications

Future commands:

- `wiki curate plan --workspace PATH --json`
- `wiki curate validate --workspace PATH`
- `wiki curate prompts --workspace PATH`
- `curator_plan_workspace(workspace_path)`
- `curator_check_workspace(workspace_path)` should return parsed spec summary
  and spec hash.

## 7. Plugin UX Implications

The plugin should display:

- active workspace;
- spec hash;
- active Exhibition;
- allowed retrieval modes;
- prompt profile;
- source scope warnings;
- validation errors.

The plugin should not silently invent workspace scope when the active note is
outside a workspace.

## 8. Migration From Current curate.yml

Existing files should remain valid.

Migration rule:

- missing new fields use safe defaults;
- current `persona.domain`, `persona.subdomain`, `persona.goal`,
  `disambiguation_keywords`, and `confidence` map into new `knowledge`,
  `goal`, and `verification` sections;
- old `min_confidence` remains accepted;
- old `exhibition` remains the active Exhibition pointer.

## 9. Acceptance Criteria

The spec evolution is ready when:

- current `curate.yml` remains readable;
- new fields are documented;
- prompt builders know how each field is used;
- `curator_check_workspace` can expose spec state;
- tests cover source policy, false-merge warnings, output contract, and
  backprop policy.


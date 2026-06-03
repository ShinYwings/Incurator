# Backprop And Insight Lifecycle Plan

## 1. Purpose

Backprop is an Incurator identity feature. v0.3.1 should make it more precise by
separating corrections, contradictions, new derived insights, style-only edits,
and promotions.

The core rule remains:

Source truth must not be polluted by later derived insight.

## 2. Lifecycle Categories

### 2.1 Correction

A correction means a generated Curator artifact misrepresented its evidence.

Example:

- An Atom says a paper reported top-1 accuracy when the source only reported
  top-5 error.

Action:

- patch generated knowledge;
- trace affected concepts/Exhibitions;
- invalidate dependent caches/reports;
- preserve original source text.

### 2.2 Contradiction

A contradiction means two sources or generated artifacts conflict.

Example:

- Source A claims method X is stable under condition C.
- Source B claims method X fails under condition C.

Action:

- record contradiction;
- flag affected units/concepts;
- surface in Exhibition;
- require review if merge would erase disagreement.

### 2.3 New Derived Insight

A new derived insight is not a correction to the original source. It is a later
interpretation or synthesis.

Example:

- A workspace discussion interprets ResNet residual blocks through Neural ODEs.
  The original ResNet paper did not make that claim.

Action:

- create an insight candidate;
- attach provenance to the discussion, Exhibition, or promoted note;
- optionally promote to `02_Wiki/`;
- do not rewrite original ResNet source context as if it contained the insight.

### 2.4 Style-Only Edit

Style-only edits improve presentation without changing claims.

Action:

- update the edited artifact if allowed;
- do not trigger expensive backprop;
- record minimal trace.

### 2.5 Promotion Request

Promotion means the human wants a generated or conversational artifact to become
durable human-facing knowledge.

Action:

- write to `02_Wiki/`;
- mark promotion provenance;
- re-ingest on next add/build if needed;
- do not mark all cited generated nodes as human verified automatically.

## 3. Backprop Prompt Diagnosis

The first prompt in any backprop flow should classify the change.

Inputs:

- previous generated artifact;
- updated artifact;
- linked evidence;
- `curate.yml` backprop policy;
- source spans;
- human request if present.

Output:

```json
{
  "classification": "correction | contradiction | derived_insight | style_only | promotion_request | ambiguous",
  "confidence": 0.0,
  "affected_nodes": [],
  "source_truth_impact": "none | source_misread | source_conflict | unsafe",
  "recommended_action": "patch_generated | flag_review | create_insight_candidate | promote | no_op",
  "reason": "..."
}
```

## 4. Insight Candidate Schema

Insight candidates should record:

- candidate id;
- created at;
- workspace;
- source Exhibition/query/conversation;
- text;
- claim type;
- supporting sources;
- missing sources;
- related concepts;
- confidence;
- review status;
- promotion status;
- backprop status.

Insight candidates are not human truth.

## 5. Backprop Events

Backprop events should record:

- event id;
- trigger type;
- triggering artifact;
- classification;
- affected nodes;
- prompt trace ids;
- patch plan;
- applied changes;
- skipped changes;
- review requirements;
- timestamps.

## 6. Patch Planning

Patch plans should be explicit:

- generated nodes to patch;
- generated nodes to invalidate;
- reports to refresh;
- Exhibitions to refresh;
- caches to clear;
- human-verified nodes to preserve;
- sources that must remain unchanged.

## 7. Source Truth Policy

The system must distinguish:

- source-authored claim;
- generated interpretation;
- workspace-derived insight;
- promoted human knowledge.

Rules:

- Do not edit `03_Notes/` autonomously.
- Do not edit `04_Resources/` autonomously.
- Do not rewrite source map to include later insight.
- If derived insight needs an L1-like source, it must come from a promoted note,
  conversation artifact, or explicit human-created source.

## 8. Relationship To Exhibitions

Exhibitions are valid backprop triggers because they are where source knowledge
meets workspace context.

However:

- editing an Exhibition does not prove the source changed;
- a new Exhibition insight may belong to an insight candidate;
- only source-grounded corrections should propagate into lower generated claims;
- human-verified promoted Exhibitions must be protected.

## 9. Tests

Required future tests:

- correction updates generated Atom/Concept but not source text;
- derived insight creates candidate instead of rewriting original CTX;
- contradiction flags both sides;
- style-only edit produces no expensive rebuild;
- promotion writes `02_Wiki/`;
- ambiguous classification requires review;
- source truth policy is enforced for ResNet/Neural ODE testbed.

## 10. Acceptance Criteria

Backprop lifecycle design is accepted when:

- all feedback types are distinguishable;
- prompt contracts enforce classification before patching;
- source truth remains immutable;
- insight candidates are provisional;
- promotion is explicit;
- trace records every backprop decision.


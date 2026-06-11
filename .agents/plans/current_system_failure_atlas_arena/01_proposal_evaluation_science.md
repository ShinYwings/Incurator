# Evaluation Science Proposal: Ground Truth, Holdouts, And Decision Rules

Date: 2026-06-11 | Agent Persona: evaluation_scientist
Status: DRAFT PROPOSAL

## 1. Core Logic & Implementation

### Ground-truth hierarchy

1. deterministic expected record/span/locator ids where the fixture controls
   identity;
2. claim-to-minimal-support labels for provenance correctness;
3. graded relevance judgments for ranking;
4. route/task labels and expected multi-hop paths;
5. hard negatives and contradiction labels;
6. sampled human review for semantic judgments;
7. calibrated model judges only as secondary diagnostics.

### Dataset partitions

- **development**: visible cases used to build and debug the observatory;
- **frozen regression**: stable cases used at every release gate;
- **holdout**: labels hidden from tuning decisions;
- **adversarial**: homonyms, contradictions, stale anchors, irrelevant bridges,
  formulas, Korean/CJK, missing providers;
- **live-vault sample**: opt-in human-reviewed sample, never the sole gate.

### Threshold policy

No threshold becomes a release gate before:

- the labeling method is documented;
- the current baseline is measured;
- expected variance is measured for LLM-sensitive cases;
- the user approves the threshold or the evidence-backed revision.

Program 1 seed thresholds from the umbrella plan:

- 100% selected source-supported evidence has resolvable record/span identities;
- 0 fabricated working-looking links;
- citation correctness at least 95%;
- citation completeness at least 90%;
- deterministic repeatability under unchanged corpus/config/model.

These are provisional until the baseline and labeling procedure are approved.

### Comparison rule

Every candidate change report must include:

- before/after on the same snapshot and oracle version;
- per-family deltas;
- hard failure count;
- degraded-mode impact;
- latency/token/cost deltas;
- statistical or repeated-run treatment for nondeterministic stages;
- explicit "no decision" when evidence is insufficient.

## 2. Pros & Cons

### Pros

- Prevents overfitting to one anecdotal query.
- Separates deterministic correctness from semantic judgment.
- Makes user-approved release gates defensible.

### Cons

- Human labeling is slow and must be maintained.
- Frozen fixtures can become stale as contracts intentionally evolve.
- Strict gates may delay visible fixes until measurement is trustworthy.

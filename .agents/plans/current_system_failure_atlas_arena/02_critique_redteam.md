# Critique On Current-System Failure Atlas Proposals

Date: 2026-06-11 | Agent Persona: red_teamer
Status: DRAFT CRITIQUE

## 1. Vulnerabilities & Flaws

### R1 - The observatory can become a shadow product

The proposals risk building a generalized analytics platform before proving that
the minimum diagnostics need it. Program 1 must not create dashboards, generic
event buses, or long-lived schema merely because they may be useful later.

### R2 - Reproductions may encode implementation details as truth

A fixture that expects current row ids, route names, or trace shape can preserve
the very defect later programs need to remove. Oracles must assert stable
behavioral contracts and minimal identities, not incidental formatting.

### R3 - One authoritative QTR is a desired contract, not current evidence

The atlas must first reproduce the disconnected-trace behavior. It cannot rewrite
or merge traces during collection and then claim the current system is
reproducible.

### R4 - Span existence can still masquerade as support

The proposed valid-span rate is weak. A broad upstream span can exist, resolve,
and still fail to support the claim. Claim/span entailment labels and exact
evidence inspection are mandatory.

### R5 - Live provider results can make release gates flaky

LLM, embedding, and reranking providers may change outputs or be unavailable.
Provider-free deterministic gates must remain separate from optional/live
quality measurements.

### R6 - Testbed rewrite can destroy historical evidence

The old scenario is stale, but replacing it carelessly can erase useful source
fixtures and examples of prior architectural assumptions. Inventory first;
create current scenarios separately; delete only through the later approved
workflow.

### R7 - Cross-client parity can be falsely defined as byte equality

Obsidian has immediate selected/open-view context that external agents do not.
Parity must compare the normalized backend evidence transaction for an
equivalent request, while preserving client-specific immediate context.

### R8 - Diagnostic artifacts may leak private vault content

Evidence bundles can accidentally persist full live-vault text or external
Reference Mode sources. Default to synthetic/testbed fixtures and hash/reference
live evidence unless explicitly approved.

### R9 - Failure classification can hide unresolved defects

"Accepted limitation" and "assigned downstream" can become labels used to close
hard problems. Each such status needs an owner, explicit contract, impact,
quality risk, and blocking dependency.

### R10 - Production fixes during diagnosis corrupt the baseline

The most tempting defects, especially F1, are easy to patch. Doing so before the
baseline and fixture are captured destroys the current-system evidence and
violates the planning/diagnostic boundary.

## 2. Suggested Alternatives

- Require a minimum-substrate justification for every observatory code change.
- Version oracles separately from implementation schema.
- Capture "before" evidence before any approved repair.
- Separate deterministic CI gates, provider-sensitive benchmarks, and manual
  semantic review.
- Preserve client-specific context while comparing normalized backend packs.
- Require explicit downstream acceptance records rather than generic deferral.
- Store only testbed evidence by default and declare privacy/retention policy.

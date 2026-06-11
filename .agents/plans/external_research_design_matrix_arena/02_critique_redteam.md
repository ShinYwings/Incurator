# Critique On External Research Design Matrix Proposals
Date: 2026-06-11 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

### Failure-first research can encode current-system bias

Starting only from known failures risks missing a simpler architecture or a
failure not represented in current fixtures. The candidate list could become a
confirmation exercise for the umbrella plan.

### Disposable spikes can produce false confidence

An isolated PPR, hierarchy, or contextual-chunk spike may omit integration costs,
staleness behavior, and real production constraints. Conversely, it may perform
poorly because it lacks the reference system's supporting components.

### Benchmark leakage remains likely

The same agent may author fixtures, tune spikes, and interpret results. Small
private-vault gold sets invite overfitting and post-hoc metric selection.

### Primary sources are not neutral

Official papers and implementations often report favorable settings and omit
negative operational details. "Primary-source only" can become vendor-claim
repetition unless claims are bounded and independently reproduced.

### Adopt/benchmark/reject is too coarse

A technique may be useful only for one route, source type, or scale. A global
label can overstate a result. "Adopt as design principle" can smuggle an
implementation commitment into a planning-only program.

### Cost and update behavior may be under-tested

Tiny frozen fixtures cannot reveal graph blow-up, eager summarization cost, or
incremental invalidation problems. Provider-dependent models make cost results
unstable.

### Research code may contaminate the workspace

Even disposable scripts can become de facto production dependencies or mutate
the testbed/database if boundaries are not explicit.

## 2. Suggested Alternatives

- Add an open-question scan and architecture-neutral control before candidate
  evaluation.
- Require route- and failure-scoped decisions, never global labels without
  evidence.
- Separate fixture authoring, spike execution, and decision review roles.
- Freeze holdouts before candidate tuning and require a final untouched run.
- Add scale/update simulations and extrapolation limits to every dossier.
- Distinguish "adopt contract/invariant" from "authorize implementation."
- Run spikes only against copied/exported fixtures with mutation guards.
- Require one skeptical counter-source or independently reproduced limitation
  where available, while preserving primary sources as claim authority.

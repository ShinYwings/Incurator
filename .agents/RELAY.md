# RELAY — v0.37.1 RELEASE HANDOFF

## Goal

Continue the System Stability Overhaul through independently reviewable
integrity releases. Query Provider Failure UX is complete in v0.37.1;
authored-wikilink architecture validation is the next workstream after merge.

## Plan Reference

- Umbrella: `.agents/plans/01_system_stability_overhaul.md`
- Evidence: `.agents/plans/01_roadmap_evidence.md`
- Current branch: `release/v0.37.1`
- Completed slice history: v0.37.1 branch commits (active plan artifacts are
  removed in the release commit)

## Analysis & Reasoning

- Provider output is accepted only after successful process completion and
  non-blank validation; all `LLMError` subtypes participate in failover.
- The query boundary catches only expected provider failures after a QTR exists,
  then retains failed PTRs, evidence provenance, warnings, and failed synthesis
  actions without hiding the original diagnosis.
- CLI, MCP, hidden-plugin JSON, and plugin UI use the existing failure envelope;
  unexpected runtime/storage defects still propagate.

## Progress Status

- v0.37.0 merged in PR #98 and the release branch was cleaned.
- v0.37.1 implementation, EN/KR docs, TDD, code review, version sync, changelog,
  and testbed validation are complete.
- Final gates: backend 1,325 passed; plugin 725 passed; Ruff and Mypy passed;
  production build passed; npm audit found zero vulnerabilities.
- ResNet testbed lint scored 100/100, and an authenticated Antigravity query
  printed its non-streaming answer and exited 0 without a traceback.
- The release branch is ready for PR review and merge.

## Critical Context / Blockers

- Cancellation trace finalization, trace-storage outage recovery, malformed
  provider wire shapes, prompt-provider attribution, early Antigravity temp-log
  cleanup, and generic no-JSON plugin command handling remain deferred.
- Authored-wikilink validation remains a separate release and must first
  reconcile the conflicting Failure Atlas F9 meanings.

## Immediate Next Action

Review and merge the v0.37.1 PR from `release/v0.37.1`. After merge, update
local `master` and begin authored-wikilink architecture validation from that
clean base.

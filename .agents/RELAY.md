# RELAY — IDLE

## Goal

None (System IDLE).

## Plan Reference

- None

## Analysis And Reasoning

- v0.41.0 (local read-only PDF page reader for Ask AI and Sidechat) shipped and
  merged to master via PR #109.
- Code review on that PR found the feature inert on the popover (a hardcoded
  `toolPolicy` literal that had drifted from `POPOVER_PROFILE`) plus a coupled
  CLI-sandbox fail-open and two document-identity races; all four were fixed in
  `930b38f` before merge, and PLUGIN_SCHEMA §13.7 now states the three
  enforcement points that were missing.

## Progress Status

- Shipped v0.41.0.
- System is idle awaiting new task/report triage.
- Agreed next step is a deep system-defect audit (documented-scenario
  conformance plus the regression audit's P9 release-chain dry pass, run as one
  sweep) feeding `USER_REPORT.md` and then ROADMAP items 1-2 — but the user has
  explicitly put it ON HOLD. Do NOT start it without a new instruction. No plan
  authored yet.

## Critical Context / Blockers

- None.

## Immediate Next Action

Wait for user task or new inbox triage in USER_REPORT.md.

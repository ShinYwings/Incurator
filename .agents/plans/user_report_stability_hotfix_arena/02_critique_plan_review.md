# Critique on Initial User-Report Stability Plan

Date: 2026-06-25
Agent Persona: Reviewer / Red Team

## 1. Vulnerabilities & Flaws

- **VLM sanitizer placement is underspecified.** "Sanitize defensively" does not
  say where the sanitizer runs. It must run after VLM generation and before any
  generated text is persisted into parsed page metadata, source spans, CTX pages,
  or cache. A naive regex may corrupt valid Markdown images or real external URLs.
- **L2 English enforcement is too weak.** Prompting alone cannot guarantee English
  output when the source/context is heavily Korean. The plan needs a programmatic
  guard that fails and retries non-English generated fields.
- **`source rm` default behavior needs caller audit.** Changing defaults without
  auditing internal callers risks breaking any cleanup path that implicitly relied
  on source-file deletion.
- **L4 generation ambiguity is evasion.** The plan must answer whether L4 is
  automatic or manual in current architecture, then diagnose the reported behavior
  against that contract.
- **Arena structure was violated.** Domain analysis files were written directly
  under `.agents/plans/` instead of the arena folder.

## 2. Suggested Alternatives

- Move domain analysis docs into
  `.agents/plans/user_report_stability_hotfix_arena/`.
- Add an explicit sanitizer contract:
  post-generation, pre-persistence, Markdown-aware enough to remove only
  `file://` or configured `.cache/vision_render` temp destinations.
- Add deterministic English validation for generated L2/KNU/Atom fields with
  capped retry and explicit layer error on repeated failure.
- Add a `remove_source` call-site audit step before changing defaults.
- State L4 contract directly: Add Source is not a full build; `wiki build` /
  worker should run global L3 and L4 automatically; no eligible community reports
  can yield zero SYN nodes by design, but perpetual `l4_status='pending'` after a
  completed build is a status bug.

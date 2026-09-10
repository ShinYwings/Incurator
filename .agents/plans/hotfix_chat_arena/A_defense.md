# Defense / Revision: A_latency after B critique
Date: 2026-09-10 | Agent Persona: Performance / Frontend Engineer

## 1. Accepted Findings

- Parallelize backend/context reads only. No concurrent LLM calls, no shared settings mutation, no request/global image-state changes. Attach a catch immediately to early evidence work and let a failed optional fetch produce the existing unavailable response/log rather than an unobserved rejection.
- Capture the knowledge flag at Send before image/materialization awaits; carry it as a method parameter through prompt and evidence assembly. Capture workspace and PDF tabs before starting concurrent preparation. The public toggle means **automatic prior-knowledge lookup**; explicit attached documents, wikilinks, page references, and deliberate tool requests remain usable. Off prompt removes the automatic-MCP addendum and explains the narrower contract.
- The user's sections 4.2–4.6 question explicitly needs prior notes. Do not suppress retrieval by an edit/question keyword guess or deadline. Existing enabled behavior remains; off is the user's explicit choice.
- Preparation scheduling cannot fix five minutes spent in agy generation. Provider agent's actual JSON delta streaming and tool-progress reporting are a necessary complementary fix; no claim that shorter preparation alone resolves that report.

## 2. Implementation Scope Locked

Implement the small frontend changes after synthesis: persisted default-on toggle, Plan removal, one per-turn workspace consultation outside PDF loop, early evidence fetch while document context resolves, corresponding docs and deferred-promise regression tests. Keep current retrieval ranking/translation contracts and current popover evidence ceiling. Do not add a provider call, dynamic model discovery, or broad cache whose staleness contract cannot be tested in this hotfix.

## 3. Validation Boundaries

Deferred promises prove concurrent scheduling and toggle behavior. A live agy generation probe proves provider response latency and streaming behavior separately. Full suite and TypeScript check are required because deleting ChatMode affects source and settings fixture types. Original untracked E4 draft stays untouched.

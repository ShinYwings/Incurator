# Defense And Consensus

Date: 2026-06-19 | Agent Persona: system_synthesizer

## 1. Resolved Design

The fix will implement a narrow sidechat edit-loop prompt contract and tests.

The first implementation will not hard-block responses that omit a heading. The
risk of blocking valid edits across providers is higher than the benefit for
this patch. Instead, the release gate is a prompt-contract test plus a sidechat
rendering/edit-review regression test where practical.

Canonical visible labels are:

```text
Analysed
Reviewed
Updated
Reviewed
```

The labels remain English for stable tests and provider consistency. Bullet
content should follow the latest user request's output language.

## 2. Non-Negotiable Boundaries

- No direct file writes by the model or tool path.
- No raw chain-of-thought request.
- No broad prompt architecture rewrite.
- No backend schema/API change.
- Docs and tests must ship with the code change.

## 3. Implementation Decision

Add a pure prompt helper and append it only for latest-turn Markdown edit
requests with an editable target. Keep the existing Diff Viewer review flow.
Document this as the expected sidechat edit-review protocol in plugin specs and
guides.

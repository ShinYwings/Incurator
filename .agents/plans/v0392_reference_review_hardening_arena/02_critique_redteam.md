# Critique on Exact-Evidence and Focus-Gated Resolution
Date: 2026-08-01 | Agent Persona: Red Team Reviewer

## 1. Vulnerabilities & Flaws

- Merely checking the final method name is insufficient if a prior exact match
  is overwritten during later scans. The implementation must preserve the
  first exact target and fail closed only after the complete bounded scan.
- Filtering all BM25 equation matches would regress multi-number or descriptive
  equation references that are outside this hotfix. The stricter rule must be
  limited to the single-number pointers that trigger adjacent expansion.
- Treating every prompt-included PDF as focused repeats the current bug. Focus
  must derive from the active tab or an explicit matching PDF context reference,
  not visibility alone.
- Matching explicit references by basename can select the wrong document when
  two external folders contain identical filenames. Existing canonical source
  identity/path comparison must be reused.
- Source-string tests alone would not prove runtime behavior. At least one test
  must execute the relevant policy/resolution path.

## 2. Suggested Alternatives

- Track whether the expanded equation pointer obtained exact-label evidence,
  then replace only unresolved expanded pointers after the scan.
- Extract the smallest pure eligibility predicate possible and cover it with
  table-driven tests for active PDF, explicit matching PDF, Markdown plus
  background PDF, and multiple background PDFs.
- Retain an integration source-contract assertion only as a supplement to
  behavior tests.
- Reuse the existing PDF source identity helper; stop and reassess if no stable
  identity exists rather than adding basename heuristics.

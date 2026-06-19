# Critique on Backend Proposal

Date: 2026-06-20 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

- A blind text purge can remove useful historical migration context or qmd URI
  normalization that still protects old vaults from broken links.
- Removing `qmd_*` status keys is an API change. If the plugin is not updated in
  the same branch, dashboards and status bars can falsely report offline search.
- A guard test that literally contains the legacy token can defeat the stated
  grep success condition.
- Deleting benchmark parity material can erase useful evidence for why the
  DB-native engine exists.

## 2. Suggested Alternatives

- Preserve behavior where possible by generalizing names and parsers rather than
  deleting logic. For example, replace one scheme-specific URI regex with a
  scheme-generic legacy URI regex.
- Update backend, plugin, tests, and docs in the same branch.
- Write guard tests using a constructed forbidden token so the guard does not
  itself create a match.
- Treat `docs/benchmarks/` as historical evidence outside the active functional
  grep gate unless the implementation can update it cleanly without losing the
  historical comparison.


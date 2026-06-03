# Bugfix.md Resolution Plan - 2026-06-02

## Goal

Resolve the remaining `.agents/bugfix.md` items as one staged bug sweep.
Implementation is approved by the user. Validation uses the
`complex_math_backprop` testbed with `deepseek-v4-flash` and low effort.

## Scope

- Remove the standalone Dashboard Devices tab and show Syncthing device-folder
  mappings only in Overview.
- Merge Incurator backend enablement and configured status into one inline
  settings row.
- Let all purple context pins be removed for the current turn, while automatic
  visible context may reappear on the next turn.
- Add eye/eye-off prompt-inclusion toggles to pinned purple chips.
- Make language handling per query: detect the latest input language, reason and
  search in English, then answer in the latest input language unless explicitly
  overridden.
- Keep query-generated EXH support, but ensure persona/context and language are
  scoped to the current question/session, not stale workspace/session state.
- Make sidechat RAG boundaries explicit: the plugin-selected agent LLM writes
  the final sidechat answer; backend RAG/query only supplies context or a
  backend synthesis when called.
- Improve Markdown edit instructions and review flow so whole-file similar
  replacements are proposed as diff hunks with Accept/Reject before mutation.
- Treat PDF crop images as temporary query context, not durable `05_Assets`
  output.
- Deduplicate Zotero/reference registration and include portable PDF links for
  Zotero-backed reference stubs.
- Store DeepSeek API keys outside the shared vault in an encrypted local secret
  store; shared config stores only a secret reference.

## Implementation Notes

- Active specs remain synchronized at v0.2.2.
- Existing dirty worktree changes are intentional and must not be reverted.
- `04_Resources` reference stubs remain portable; absolute Zotero/PDF paths stay
  in backend/device-local metadata.
- Local encrypted secret storage protects against accidental config/vault sync
  leakage, not against another process running as the same OS user with access
  to the local key file.

## Verification

- Backend: device registry, query language/EXH, DeepSeek secret-store, and
  Zotero/reference tests.
- Plugin: dashboard, settings, context chips, language bridge/provider context,
  image context, and diff-review tests.
- Testbed:
  - `wiki testbed init complex_math_backprop --force --llm deepseek-api --model deepseek-v4-flash`
  - `VAULT_ROOT=testbed wiki config provider --primary deepseek-api --model deepseek-v4-flash --effort low`
  - `VAULT_ROOT=testbed wiki status`
  - `VAULT_ROOT=testbed wiki add`
  - `VAULT_ROOT=testbed wiki sync`
  - `VAULT_ROOT=testbed wiki lint`
  - Run `reindex` and `query` only if qmd and the DeepSeek key are available.

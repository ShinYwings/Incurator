# Hotfix evidence ledger

- Rollback anchor: b4b8721, master/origin/master identical before branch.
- Branch: hotfix/chat-provider-sync; target 0.82.0 (new user setting/Plan removal).
- Existing untracked E4 draft preserved; no live vault or DB writes.
- Linux reproduction: isolated import of dev-28e419df29f2.jsonl fails `knowledge_units references unmapped source_id 32`, same as newly supplied user log. 62 retired units and 1 discarded generation survive deleted source.
- Current CLI lists: agy live lists 3.8/3.7/3.6 Flash, no 3.5. Codex model cache fetched 2026-09-10 lists Astra + 5.6 Sol/Terra/Luna + 5.5 at CLI context 272000. Official Claude Fable 5.1 page verified.
- agy live native stream equation probe: text_delta and final result observed, one turn, model duration 1.61 s; tool whitelist enforcement not yet established.
- Pre-change Codex stream bug: compares lengths across distinct agent_message items, truncating final edit proposals.
- Full plugin validation: 1278 passed, 3 skipped; tsc and production build pass. Ruff/mypy pass. First full pytest: 1962 passed, two source fingerprint tripwires; documented the deletion-only non-impact and rearmed the frozen Q06 hash (no metric/input/rerun change), both now pass; final full run pending.
- User corrected that actual usage was not depleted. Treat CLI diagnostics as reported refusal, never proof of account usage. Reproduced and fixed native stderr substring false-positive termination. Current agy /usage reports Starter Quota, Gemini remaining 0%, reset about 139 hours; entitlement correctness remains external/unverified. Direct isolated gemini-3.8-flash invocation reports same refusal; guard surfaces it at 5285 ms, process closes at 6358 ms, log removed. No extra credits or permission bypass enabled.
- Testbed smoke: VAULT_ROOT=testbed .venv-dev/bin/wiki status --json succeeds; editable source is current, installed distribution metadata is stale 0.17.0 (not a source mismatch). No production vault/config modified.

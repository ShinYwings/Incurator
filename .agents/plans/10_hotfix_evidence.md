# Hotfix evidence ledger

- Rollback anchor: b4b8721, master/origin/master identical before branch.
- Branch: hotfix/chat-provider-sync; target 0.82.0 (new user setting/Plan removal).
- Existing untracked E4 draft preserved; no live vault or DB writes.
- Linux reproduction: isolated import of dev-28e419df29f2.jsonl fails `knowledge_units references unmapped source_id 32`, same as newly supplied user log. 62 retired units and 1 discarded generation survive deleted source.
- Current CLI lists: agy live lists 3.8/3.7/3.6 Flash, no 3.5. Codex model cache fetched 2026-09-10 lists Astra + 5.6 Sol/Terra/Luna + 5.5 at CLI context 272000. Official Claude Fable 5.1 page verified.
- agy live native stream equation probe: text_delta and final result observed, one turn, model duration 1.61 s; tool whitelist enforcement not yet established.
- Pre-change Codex stream bug: compares lengths across distinct agent_message items, truncating final edit proposals.
- Full validation results: pending.

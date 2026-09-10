# RELAY

**Branch:** `master` (Ready for branch creation: `fix/e4-agy-shell-out`)

## Next Action
**ROADMAP E4 (agy shells out during graph extraction)**
PM (Gemini) has authored the deep analysis draft at `.agents/drafts/e4_agy_shell_out.md`.
Executors (Claude/Codex): 
1. Branch off `master` (e.g. `fix/e4-agy-shell-out`) if not already done.
2. Read the draft and run the Arena debate to synthesize the final `PLAN_TEMPLATE.md` for E4.
3. Update `ROADMAP.md` and this file once the plan is finalized, then proceed to TDD/Implementation.

### Update (2026-09-10, Codex — urgent user fixes)

**Current branch:** `hotfix/chat-provider-sync`. E4 remains paused; the user explicitly requested only this hotfix before roadmap work.
**Goal:** response latency + knowledge toggle / remove Plan, Antigravity denied tools, current model catalogue, Codex note diff loss, Linux sync error.
**Plan reference:** `.agents/plans/10_chat_sync_hotfix.md` and `hotfix_chat_arena/` (independent proposals and cross-critique recorded).
**Progress:** source lifecycle/transport fix replays the exact 85 MiB Mac snapshot on an isolated fresh DB in about 4 seconds: 86,694 inserts, zero rejects, 62 retired units + one discarded generation detached, all 123 QTR retained; idempotent second import. Knowledge toggle/Plan removal, parallel context preparation, native agy streaming, Codex item/diff fixes and catalogue implemented with regression tests. Actual five-minute query logs show repeated terminal Individual quota reached retries; per-invocation diagnostic guard now stops these promptly. Targeted provider tests pass. Full pytest 1962 passed; two hash tripwire failures addressed with a documented source-deletion-only rearm; ruff/mypy pass.
**Critical context:** preserve original untracked `.agents/drafts/e4_agy_shell_out.md`. No production vault/DB/snapshot writes. Agents hit account usage limits; root continues. Antigravity prompt is precise but native tool exclusion is NOT proven; retain narrow permission grants. Do not claim full prevention without live evidence.
**Next:** full plugin checks, testbed and live bounded quota probe, version 0.82.0/changelog/spec title sync, invoke code-review skill on PR, CI/review/merge. Resume no roadmap work.

# RELAY — Active Task: Cross-Device State Sync (v0.30.0)

**Branch**: `fix/zotero-profile-sync`
**Status**: PLAN AUTHORED — **STOPPED for user approval** before coding.

**Goal**: Make Zotero profiles AND the knowledge DB sync across the user's
linux + macOS devices. Both symptoms (profiles differ per device; Dashboard
Sources shows 5 not 31) share one root cause: `.stignore` excludes `data.json`
and `.curator/state.sqlite`.

**Decisions locked this session**:
- Sync `state.sqlite` (user chose this over thin-client/rebuild).
- DB paths verified portable — zero absolute paths in any table; reference paths
  use `path_refs.py` `@root_key` + Zotero identity keys, resolved per-device.
- Write-safety: **checkpoint-truncate WAL on close + last-write-wins**.
- Part A profiles → `.curator/zotero_profiles.json` (sessions.json pattern).

**Artifacts**:
- Master Plan: `.agents/plans/06_cross_device_state_sync.md`
- Arena briefing: `.agents/plans/cross_device_state_sync_arena/00_problem.md`
- Draft (Part A): `.agents/drafts/zotero_profile_sync.md`

**Immediate Next Action (on approval)**: Execute P0 (baseline + rollback anchor
+ RED test) → P1 docs-first specs (STOP again for schema approval) → P2 backend
checkpoint/guard → P3 plugin profile migration → P4/P5 integration + testbed.

**Do NOT** start coding until the user approves the plan.

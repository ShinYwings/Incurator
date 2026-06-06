# Relay State — fix/v0.3.3-cleanup (2026-06-06, Claude Code)

## Status: Wrapping up — ready to merge PR #3

Branch: `fix/v0.3.3-cleanup`  
PR target: `master` — https://github.com/ShinYwings/Incurator/pull/3

## What was done this session

**Workflow infrastructure (8 issues fixed):**
- GitHub Actions CI, PR template, branch naming convention, master vs main note
- relay.md IDLE Cleanup rule, System Invariants updated, schema_guardian fix
- Rollback procedure, Shared Architecture Memory section
- Full CLAUDE.md sync with AGENTS.md

**Docs cleanup:**
- Removed stale `wiki curate` and `wiki reindex (QMD)` references from CLAUDE.md, AGENTS.md
- Fixed `backend/pyproject.toml` readme path (root README deleted → `docs/README.md`)

**Roadmap cleanup:**
- Stripped version numbers from all plan skeleton files (02, 03, 04, roadmap)
- Reordered roadmap: Knowledge Sync Bridge (03) is now milestone 1, Stabilization (02) is milestone 2
- Linked user_report items 3-7 to 02_stabilization.md
- Removed item 1 (GitHub 연동) from user_report — fully implemented and verified

## Immediate Next Action

Merge PR #3 on GitHub. After merge, reset this file to a minimal IDLE stub and start the next batch from user_report.md following the Universal Strict Workflow.

**Next batch candidates (user_report To-Do):**
- Priority items per roadmap: Knowledge Sync Bridge (no user_report item yet — may need to add one)
- Otherwise: items 2, 9, 10 (minor/standalone), or items 3-7 (major/RAG stabilization batch)

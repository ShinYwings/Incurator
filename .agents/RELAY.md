# Cross-Agent Relay State

## Status: ACTIVE
**Milestone:** Chat Context Decay & Minor Quick Wins
**Branch:** `feature/chat-decay-quick-wins`

**Target Drafts:**
- `.agents/drafts/chat_context_decay.md`
- `.agents/drafts/minor_quick_wins.md` (Note: Web Search feature is EXCLUDED)

**Progress (2026-06-21, Claude Code):**
Arena Workflow complete. Authored:
- Debate: `.agents/plans/chat_decay_quick_wins_arena/` (00_problem → proposal → redteam critique → defense)
- Master Plan: `.agents/plans/01_chat_decay_quick_wins.md`
- Evidence Ledger: `.agents/plans/01_chat_decay_quick_wins_roadmap_evidence.md`

Key finding: chat-decay is ~80% solved by v0.19.0's recency anchor. Residual root
cause is a prompt contradiction — a `Cmd+Shift+L` `line-range` ref is BOTH primary
context (anchor: "don't edit") AND an editable ref (`<editable_selection>` +
`<edit_review_loop>`: "you may edit"). Fix = suppress edit affordances on a fresh
localized question turn so the anchor is unopposed. Scope: 3 plugin-only items
(chat decay, LaTeX fast/light model, Zotero profile recent-first). Minor bump
`0.20.0 → 0.21.0`. Web Search EXCLUDED.

**Next immediate action:** AWAITING HUMAN APPROVAL of the Master Plan before any
code (Universal Strict Workflow Step 4 STOP gate).

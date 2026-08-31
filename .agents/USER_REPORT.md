# User Report

This document is a **plain Inbox (backlog) log** that records bugs reported by the user, required features, ideas, etc., in chronological order without any filtering.

Agents must check this document and triage the received items into the `To-Do (Queuing)` area or `Icebox` area of `.agents/ROADMAP.md`. Once the triage is complete, **immediately delete** the item from this document.

---

## 📝 User Inbox

_(empty — last triaged 2026-09-01)_

Four items were resolved or moved on that date:

- The popover reference-lookup failure shipped in **v0.77.0**.
- Tests writing into the real home config were fixed in **v0.76.0**
  (`conftest.py` now isolates the home and global config dirs and blocks the
  provider CLIs).
- The provider key travelling as a CLI argument became **ROADMAP E7** — verified
  still open before moving, not assumed.
- `is_knowledge_question` gating nothing became **ROADMAP E8** — likewise
  verified against the code first.

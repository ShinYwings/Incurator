# User Report

This document is a **plain Inbox (backlog) log** that records bugs reported by the user, required features, ideas, etc., in chronological order without any filtering.

Agents must check this document and triage the received items into the `To-Do (Queuing)` area or `Icebox` area of `.agents/ROADMAP.md`. Once the triage is complete, **immediately delete** the item from this document.

## 📝 User Inbox

- **2026-07-30 — Plugin `npm audit` exits with an error.** Running the audit in
  `plugin/` reports one high-severity advisory for transitive
  `postcss@8.5.15` (`GHSA-r28c-9q8g-f849`). Fix the lockfile without adding
  PostCSS as a direct runtime dependency or applying unrelated package upgrades.

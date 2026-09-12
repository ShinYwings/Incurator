# B1/B2 Retention Follow-up Briefing

Date: 2026-09-11 | Baseline: master `218176e3`, v0.82.5

## Problem

The user requested relay continuation. USER_REPORT.md is empty, but ROADMAP.md
queues B1/B2 retention first. The relay's IDLE label does not reflect this queue.
Determine the actual remaining work from current code and contracts before
implementing another retention feature. Historical B2 figures and proposed
defaults are evidence of past findings, not current policy or measurements.

## Existing constraints

- `wiki gc plan/run`, session retention, the unreferenced prompt-run cap, and a
  conservative temporary empty-vault cache sweep already exist.
- Preserve full active-session replay, including image thumbnails. The user
  explicitly reverted a history window in v0.82.3.
- Session retention is chosen by the user; prompt-run policy was delegated to
  the agent. Do not silently choose deletion windows for other user-visible
  history. Actual production data deletion or migration requires authorization.
- DB and session tombstones cannot expire without a proven cross-device
  acknowledgement/recovery protocol. An offline mount is not a dead vault.
- Plan one contract change per release; prefer fewer moving contracts when
  capability is equal. Escalate an actual product tradeoff with concrete choices.
- Read the relevant guides/specs and current implementation. Trace references
  by semantics, including differently named and JSON-embedded identifiers.

## Arena assignments and deliverables

Independent proposals: backend/schema retention, plugin/session behavior, and
adversarial synchronization/cache safety. Use PLAN_TEMPLATE.md's proposal
skeleton and cite file/line evidence. Each proposal must distinguish shipped
behavior, defects, missing capabilities, and decisions still requiring the
user. Then cross-critique another proposal and defend/revise your findings.
No application code, configuration changes, live GC, vault writes, or migrations
during this planning phase. Each agent owns only its assigned arena files.

## Definition of done for planning

A template-compliant master plan, domain analyses and evidence ledger identify
the smallest justified next release, exact behavior, tests/docs, and any real
decision preventing implementation. If current evidence cannot justify a policy
without removing useful history, make that fork explicit instead of inventing
a default or calling the entire retention queue complete.

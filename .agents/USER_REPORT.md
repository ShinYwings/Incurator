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

## 2026-09-03 — A question about a paper was answered with "No Git history found"

**Reported live.** Asking the sidechat to expand a derivation ("수식 9가 어떻게
10으로 **바뀌었는지** 크로네커 곱 원리에 대해서도 적고") returned:

> No Git history found for Users/shin/Library/Mobile Documents/com~apple~CloudDocs/
> Zotero/[Project] COLMAPFreeReconstruction/Major/Ray-Space Projection Model for
> Light Field Camera2019 - Zhang et al. - .pdf.

**Cause, measured against the real `detectGitSidechatCommand`:** the message is
routed by bare SUBSTRING match in `plugin/src/ui/gitSidechatCommands.ts`.
`isHistoryRequest` matches `"바뀌"` — a fragment of 바뀌다, one of the most common
Korean verbs. The whole message is then discarded and replaced with `git log` on
the active file.

Measured hijacks of ordinary questions:

| message | routed as |
|---|---|
| `수식 9가 어떻게 10으로 바뀌었는지 설명해줘` | history |
| `이 논문이 예전에 나온 방법과 뭐가 달라?` | history |
| `what is the history of this formulation?` | history |
| `변경사항 없이 그대로 쓰면 되나?` | history |
| `push-broom 스캐너와 비교하면?` | **push** |
| `the push broom model rectifies each row` | **push** |

**The push case is the serious one.** `isPushRequest` is `/\bpush\b/`, and
"push-broom" is ordinary vocabulary in this user's own field (light-field and
camera geometry). It reaches `git_manager.push()`, which runs `git push` on the
**vault repo** with no confirmation. An innocent question could publish the
user's notes to a remote.

**Secondary:** the target was a PDF inside the Zotero folder, which is not in any
git repository, and nothing checks that before answering. The path in the message
also lost its leading `/`.

**Not the root cause:** "the `바뀌` keyword is too broad". Tightening keywords is
whack-a-mole. The root cause is that a substring matcher is used as an intent
router, running BEFORE and INSTEAD of the model that could actually tell a git
request from a physics question — and for `push`, it takes an irreversible,
outward-facing action on a guess, with no confirmation and no visible signal that
the message was hijacked.

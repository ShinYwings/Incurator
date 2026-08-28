# User Report

This document is a **plain Inbox (backlog) log** that records bugs reported by the user, required features, ideas, etc., in chronological order without any filtering.

Agents must check this document and triage the received items into the `To-Do (Queuing)` area or `Icebox` area of `.agents/ROADMAP.md`. Once the triage is complete, **immediately delete** the item from this document.

---

## 📝 User Inbox

_(empty — last triaged 2026-08-23; the two remaining items became ROADMAP 19 and 20)_

- [코드리뷰 findings, 2026-08-29] 플러그인 provider 키가 CLI argv로 전달됨
  (`incuratorClient.ts` `setSecret` → `["plugin","secret","set","--value", key]`).
  argv는 `ps`에 노출된다. macOS는 `kern.procargs2`로 타 사용자의 argv 읽기를
  막으므로 실제 노출은 **동일 uid 한정**이고, 그래서 v0.71.0 리뷰에서 LOW로
  분류했다. 고치려면 stdin(또는 env)으로 값을 넘겨야 하는데, 그 경로는
  `main.ts:1058 runBackendJsonCommand` → `runBackendCommand`, 즉 **모든 백엔드
  호출이 공유하는 spawn**이다. LOW 하나 때문에 릴리스 도중 공유 경로의 시그니처를
  바꾸는 것은 안정성 타이브레이커에 어긋나므로 별도 항목으로 뺀다.
  할 일: `runBackendCommand`에 선택적 stdin 채널을 추가하고, `wiki plugin secret
  set`에 `--value -`(stdin 읽기)를 더한 뒤 `setSecret`만 그쪽으로 옮긴다.
  기존 `--value` 경로는 백엔드 자체 사용을 위해 남긴다.

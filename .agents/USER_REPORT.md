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

- [코드리뷰 findings, 2026-08-29] `is_knowledge_question`이 퍼널에서 아무것도
  게이트하지 않는다. `context_service.context_fetch`는 이 값을 derive해서
  request와 query trace에 싣지만, 651행의 `build_evidence` 호출은 조건 없이
  실행된다. 즉 비영어 "이 문단 번역해줘: <본문>" 류 메시지에서 `search_query`가
  비고 → `working_query`가 원문 본문으로 폴백 → **번역 요청 본문에 대해 BM25가
  돈다.** `plugin_api/context.py:64`는 같은 판정으로 이미 빈 pack을 반환하므로
  두 경로의 동작이 서로 다르다.
  v0.71.0에서는 docstring이 이 사실을 정직하게 말하도록만 고쳤다. 게이트 자체는
  retrieval을 통째로 건너뛰는 **제어 흐름 변경**이라 CLAUDE.md의 trivial-nit
  예외에 해당하지 않는다("if it touches ... control flow ... it needs a plan").
  할 일: 퍼널에도 게이트를 넣어 `plugin_api/context.py`와 동작을 일치시킨다.
  확인할 것 — 빈 pack을 받은 `QueryOrchestrator`가 무엇을 답하는지. "정보가
  없습니다"로 답하면 번역 요청에 대한 답으로 틀렸다.

- [코드리뷰 findings, 2026-08-29] 테스트가 사용자의 실제 홈 설정에 썼다.
  `~/.gemini/antigravity/mcp_config.json`의 `incurator` 항목이 `VAULT_ROOT`를
  `/private/var/folders/.../pytest-of-shin/pytest-1023/test_plugin_models_pull_report0/vault`
  로 가리키고 있었다 — 이미 삭제된 pytest 임시 디렉터리다. 즉 어떤 테스트가
  `Path.home()`을 monkeypatch하지 않은 채 `_sync_mcp_configs`(또는 그 경로를
  쓰는 코드)를 호출해 실제 홈 디렉터리를 오염시켰다.
  영향: 사용자의 agy MCP 등록이 존재하지 않는 vault를 가리키게 된다. v0.71.0에서
  `config/mcp_config.json`까지 쓰게 되면서 잘못된 항목이 퍼질 범위도 넓어졌다.
  할 일: 홈 디렉터리에 쓰는 테스트를 찾아 `monkeypatch.setattr(cli.Path, "home", ...)`
  를 강제하고, 홈 경로 쓰기를 막는 autouse fixture를 conftest에 넣는 것을 검토한다.

# User Report

This document is a **plain Inbox (backlog) log** that records bugs reported by the user, required features, ideas, etc., in chronological order without any filtering.

Agents must check this document and triage the received items into the `To-Do (Queuing)` area or `Icebox` area of `.agents/ROADMAP.md`. Once the triage is complete, **immediately delete** the item from this document.

---

## 📝 User Inbox

- [사용자 보고, 2026-08-31] **논문 popover에서 참고문헌 제목을 찾으려다 턴이 통째로
  죽었다.** agy가 낸 메시지:

  > jetski: no output produced — a tool required the "read_url" permission that
  > headless mode cannot prompt for, so it was auto-denied. Add an allow-rule under
  > permissions.allow in settings.json (e.g. $read_url$()). Alternatively, re-run
  > with --dangerously-skip-permissions to auto-approve all tools.

  조사 결과 (2026-08-31):

  - 필요한 조각은 **이미 전부 있다**. `incurator_fetch` MCP 서버가 사용자의
    `~/.gemini/config/mcp_config.json`에 등록돼 있고, `fetch_url` 툴을 노출하며,
    `mcp(*)` 권한도 허용돼 있다. 그 서버에는 SSRF 가드(IPv4-mapped 언매핑, DNS
    pinning)까지 붙어 있다.
  - **없는 것은 단 하나 — 모델에게 그 툴이 있다고 말해주는 문장이다.**
    `grep fetch_url`이 프롬프트 계열 파일에서 한 건도 걸리지 않는다. 그래서 모델은
    "URL을 읽어라"에 대해 agy 내장 `read_url`을 고르고, 그건 허용 목록
    (`read_file(*)`, `command(wiki)`, `mcp(*)`)에 없으므로 auto-deny → 턴 사망.
  - 이것은 v0.53.1 / v0.56.1 / v0.71.0과 **정확히 같은 계열의 네 번째 사례**다.
    다만 앞의 셋은 권한이 없어서였고, 이번엔 **권한도 서버도 있는데 안내가 없어서**다.
    권한을 하나 더 주는 방식으로 고치면 안 된다.

  결정 (에스컬레이션 아님 — 능력을 깎는 선택지가 없으므로 안정성 타이브레이커로 해결):

  - `read_url`을 허용하지 **않는다**. 그건 가드 없는 URL 페처를 신뢰할 수 없는 논문
    본문을 처리하는 경로에 주는 것이고, `incurator_fetch`를 만든 이유를 무효화한다.
  - 대신 프롬프트가 `fetch_url`을 명시한다. URL 페치 능력은 그대로 유지되면서
    가드가 걸린 경로로 간다.
  - 그리고 툴 하나가 거부됐다고 턴 전체가 빈 출력으로 끝나면 안 된다. 거부는
    모델이 가진 것으로 답하도록 degrade 되어야 한다. `crossReferenceResolver.ts`가
    이미 같은 이유로 "해결 못한 참조를 이름이라도 남긴다"를 하고 있다.

_(previously empty — last triaged 2026-08-23; the two remaining items became ROADMAP 19 and 20)_

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
  [해결됨 v0.71.0 — conftest.py + vitest.setup.ts 가드] 할 일: 홈 디렉터리에 쓰는 테스트를 찾아 `monkeypatch.setattr(cli.Path, "home", ...)`
  를 강제하고, 홈 경로 쓰기를 막는 autouse fixture를 conftest에 넣는 것을 검토한다.

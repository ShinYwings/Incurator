# User Report

## ✅ 완료된 항목 (Resolved)
- **1~8. PDF 참조 가리키기 및 UI 팝오버 버그**
  - 해결 사항: Claude Code가 `crossReferenceResolver`와 `quickQueryPopover`를 개선하여, PDF 내 "see section A4.2" 같은 텍스트나 크롭 참조를 정확히 찾아내고 ToC를 반영하도록 수정했습니다. 또한 팝업 위치가 잘리거나 새 창(Popout Window)에서 안 뜨는 문제 등 UI 관련 버그를 모두 해결했습니다.
- **10~11. 지식 정제(Synthesis) 검증 및 GraphRAG 구조 마련**
  - 해결 사항: Codex가 1차 마일스톤을 달성하여 `synthesis_audit` 서비스를 추가하고 `wiki inspect synthesis --json` 명령어로 지식 합성 과정을 추적 및 검증할 수 있는 기능을 백엔드와 대시보드에 마련했습니다.

## ⏳ 구현 대기 / 계획 완료 항목 (Planned)
- **12. GitHub 연동**
  - 상태: 아키텍처 계획 갱신 완료 (`.agents/plans/archives/2026-06_v0.3.3_github_integration.md`). 승인 후 백엔드 TDD → API → 플러그인 UI 경로 순서로 구현이 진행될 예정입니다.

## 🚀 향후 해결할 미해결 항목 (To-Do)
- **13. CLI 기능 대시보드 연동 및 설정 버그**
  - 현상: `wiki cli`에서 제공하는 기능이 Obsidian Backend Dashboard에서도 지원되어야 함. Backend AI Provider 설정이 정상적으로 변경되지 않으며, Ollama 모델 선택 시 `models.json`을 통한 추천 기능이 필요함.
- **14. CLI 명령어 통폐합 및 임베딩 자동화**
  - 현상: `wiki add`, `build`, `reindex` 등 순차적으로 진행되는 명령어들의 통폐합 필요. `jobs run` 등 불필요한 명령어들을 통합하고 비어 있는 큐에서도 빌드 시 자동 임베딩되도록 구조 개선이 필요함.
- **15. 웹 검색 기능 구현 검토**
  - 현상: 로컬 모델(Ollama, Deepseek 등) 사용 시 웹 검색 기능 연동을 지원할지 설계 및 구현 필요.
- **19. 문서 내 검색 의도 파악(라우팅) 오류**
  - 현상: "문서 위쪽을 찾아줘"와 같은 질문을 했을 때, 실제 문서의 앞부분을 검색하지 않고 상위 폴더(디렉터리)를 검색하는 쿼리 파싱 오작동 문제. 자연어 의도 파악 정확도 향상 필요.

## ✅ 추가 완료 항목 (2026-06-06, Claude Code)
- **16. 외부 참조 문서(Zotero) 중복 표시 버그** — 해결
  - 원인: Reference Mode stub 파일은 디스크에 남아 있는데 `state.sqlite`의 source 행이 사라진 경우(상태 재빌드/테스트베드 재초기화 등), DB 중복 탐지가 실패하고 `_unique_destination`이 `<name>-2.md` 중복 stub을 생성했습니다.
  - 조치: `_find_existing_reference_stub`를 추가해, stub을 만들기 전에 동일한 `logical_source_id`(Zotero는 `zotero:<key>`)를 가진 기존 stub을 디스크에서 찾아 재사용합니다. 테스트 `test_reference_import_reuses_disk_stub_when_db_row_missing` 추가.
- **17. LaTeX 렌더링 깨짐 버그** — 해결
  - 원인: 시스템 프롬프트 예시가 `` `$x = 2$` `` 처럼 백틱으로 수식을 감싸 LLM이 이를 모방했고, `normalizeLatexDelimiters`는 inline code를 보호하여 백틱 수식을 그대로 둠.
  - 조치: 시스템 프롬프트에서 백틱 예시 제거 + "수식을 백틱으로 감싸지 말 것" 명시. `normalizeLatexDelimiters`가 `` `$...$` `` / `` `$$...$$` `` 처럼 수식을 감싼 백틱을 벗겨냄(가격 표기 등 비수식은 보존). Ask AI 팝오버에도 동일 정규화 적용.
- **18. 채팅 스크롤 고정 버그** — 해결
  - 원인: 답변 완료 시 `renderMessages()`가 항상 `scrollToBottom(true)`로 강제 스크롤.
  - 조치: `renderMessages(forceScroll=true)` 파라미터화 + 재렌더 전 스크롤 위치 캡처. 생성 완료 경로만 `renderMessages(false)`로 호출해, 사용자가 맨 아래에 있을 때만 따라가고 아니면 위치 보존.
- **20. 에이전트 코드 출력 방식 개선** — 해결(2단계 모두 완료)
  - (1) 스트리밍 코드 범람 제거: `collapseStreamingEditBlocks`로 **첫 번째** edit 마커부터 모두 가려 placeholder 하나만 노출. 답변 완료 후엔 `✏️ <파일> · Review Diff` pill로 접힘.
  - (2) 영구 Diff 아티팩트 파일: `/goal` 플로우로 계획 승인 후 구현. 수정 제안이 포함된 답변이 끝나면 변경 내용을 unified-diff(```diff) 블록으로 정리한 `agent-diff-artifact` 노트를 **고정 폴더 `00_System/Agent Diffs/`**(ingest 대상 raw_dirs 바깥)에 작성하고, 채팅에 `📝 Open diff artifact` pill을 추가로 표시. 설정 토글 `editArtifactEnabled`(기본 ON), `ChatMessage.editArtifactPath`로 멱등 생성. **추가형**이라 기존 Review Diff/적용 버튼은 그대로 유지.
  - 구현: 새 순수 모듈 `plugin/src/context/editArtifact.ts`(+테스트), `chatSidebar.maybeWriteEditArtifact`/`renderEditArtifactPill`, 설정/타입, 스펙 `PLUGIN_SCHEMA_v0.3.2.md`, 가이드 EN/KR. 계획 `.agents/plans/2026-06-06_edit_diff_artifact.md`.
  - 검증: 플러그인 `tsc`/`vitest`(272 passed, 38 files)/`build` 통과. testbed에서 핵심 불변식 확인 — `00_System/Agent Diffs/...md` 노트는 `wiki add`가 인입하지 않음("No new or changed files found", source 2개 유지; 테스트 파일은 정리함). 채팅→아티팩트 생성 경로는 Obsidian 내부 실행이라 헤드리스로는 못 돌려 source-contract/단위 테스트로 커버. ![alt text](image-11.png)
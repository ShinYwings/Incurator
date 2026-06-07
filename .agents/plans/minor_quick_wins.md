# Minor Quick Wins Plan

## Linked user_report Items
이 마일스톤이 해결하는 user_report 항목:
- **[마이너 업데이트] 웹 검색 기능 구현 검토**
- **[검증 필요] L1~L4 생성 문서 내 Obsidian `[[wikilink]]` 명시적 링킹 도입 여부 검토**
- **[마이너 업데이트] Diff Viewer UI/UX 개선**

## Context
백엔드 대공사(Knowledge Sync Bridge, RAG Stabilization)와 독립적인 소규모 개선 항목들입니다. 플러그인 단독 작업이거나 연구/검증 태스크 위주이므로 빠르게 처리 가능합니다.

## Implementation Skeleton

### [마이너 업데이트] 웹 검색 기능 구현 검토
- 설계 논의 필요: 로컬 모델(Ollama, Deepseek 등) 사용 시 어떤 웹 검색 API(Brave, SerpAPI 등)와 연동할지.
- `backend/src/curator/llm.py` 또는 별도 `web_search.py` 신규 모듈 검토.

### [검증 필요] L1~L4 생성 문서 내 Obsidian `[[wikilink]]` 명시적 링킹 도입 여부 검토
- `backend/src/curator/page_writer.py` 및 `sync.py`: 기존 `()` 백링크 파싱 로직과 `[[wikilink]]` 충돌 여부 아키텍처 레벨에서 확인.
- 검증 결과에 따라 도입 여부 결정. 무작정 프롬프트를 고치지 말고 검증 후 진행.

### [마이너 업데이트] Diff Viewer UI/UX 개선
- `plugin/src/ui/diffViewer.ts`: 사용자가 직관적으로 변경사항을 수락/거절할 수 있도록 버튼/헝크 레이아웃 정리, 다크/라이트 테마 대응, 키보드 단축키 힌트 표시, 헝크 간 이동 UX 개선.
- `plugin/styles.css`: 테마별 색상 변수 정리.

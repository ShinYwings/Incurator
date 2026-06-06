# Native PDF Annotation System Plan

## Linked user_report Items
현재 user_report에 직접 대응 항목 없음 (Knowledge Sync Bridge 완료 후 진행).
구현 완료 후 관련 user_report 항목이 생기면 여기에 추가.

## Context
Zotero에 의존하던 어노테이션 시스템을 자체 시스템으로 교체합니다. 옵시디언 내장 PDF Viewer를 활용하여 하이라이트와 메모를 `state.sqlite`에 직접 저장하고 오프라인 동기화합니다.

## Multi-Agent Debate Topics (For Codex & Claude)
1. **`schema_guardian`**: 
   - `pdf_annotations` 테이블 스키마 설계 시, 옵시디언 캔버스(Canvas)와의 연동을 위해 어노테이션 블록(Block)을 어떻게 참조 가능하게 만들 것인가?
2. **`source_pair_analyst`**: 
   - 형광펜으로 밑줄 친 텍스트가 RAG 파이프라인의 `source_spans`로 직접 편입(Promotion)될 수 있도록 설계할 수 있는가?
3. **`plugin_ux_designer`** (New role): 
   - 플러그인 프론트엔드(`pdfCapture.ts` 주변)에서 Zotero의 형광펜 UX와 동일한 수준의 부드러운 하이라이팅 및 팝업 메모 UI를 어떻게 구현할 것인가? 백엔드와의 통신(IPC) 성능 최적화 방안은?

## Implementation Skeleton
- `backend/src/curator/db.py`: `pdf_annotations` 테이블 생성.
- `plugin/src/pdf/*`: 형광펜 렌더링, 이벤트 리스너, IPC 전송 로직 추가.
- `backend/src/curator/mcp_server.py` 또는 IPC 라우터: 플러그인으로부터 어노테이션 생성/조회/삭제 요청을 받아 DB에 반영.
- `backend/src/curator/db_sync.py`: `pdf_annotations` 테이블을 Knowledge Sync Bridge Export/Import 대상에 포함.

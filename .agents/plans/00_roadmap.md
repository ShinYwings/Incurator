# Incurator Master Roadmap

아키텍처 대공사를 위한 마스터 로드맵입니다. 각 마일스톤은 독립 브랜치로 작업하며, 구현 시작 전 `PLAN_TEMPLATE.md`를 따르는 상세 명세서를 별도 작성합니다.

**Global Priority Rule**: 작업 시작 전 반드시 `.agents/user_report.md`를 먼저 확인하세요. 미해결 항목이 있으면 그것부터 처리합니다.

---

## 📌 Milestones (우선순위 순)

### 1. Knowledge Sync Bridge
기기 간 지식 파편화 해결. 현재 `state.sqlite`는 기기마다 독립적으로 존재하여 지식이 쌓여도 다른 기기에서 활용할 수 없습니다. JSONL 기반 Export/Import 파이프라인과 Tombstone 충돌 해결 로직을 구현합니다.

- `backend/src/curator/db_sync.py` 신규 구현
- `wiki db export / wiki db import` CLI 추가
- 기기 종속 데이터(임베딩 등) Export 블랙리스트 정책
- 상세 명세: `03_knowledge_sync_bridge.md`

### 2. RAG & Knowledge Quality Stabilization
검색 품질과 지식 추출 정확도를 높입니다. FTS5 + Qwen3 Reranker 파이프라인 안정화, 수식 누락 문제 해결, 엔티티 중복 병합, GraphRAG급 군집화 도입을 포함합니다.

- 관련 user_report 항목: 3, 4, 5, 6, 7
- 상세 명세: `02_stabilization.md`

### 3. Native PDF Annotation System
Zotero 의존성 제거. 옵시디언 내장 PDF Viewer에 하이라이트/메모 기능을 직접 구현하고 `state.sqlite`에 저장합니다. Knowledge Sync Bridge 완료 후 진행합니다(어노테이션도 기기 간 동기화 필요).

- `pdf_annotations` 테이블 설계
- 플러그인 하이라이팅 UI + IPC 연동
- Sync Bridge Export/Import 대상에 포함
- 상세 명세: `04_pdf_annotation_system.md`

---

## 🤖 Multi-Agent Debate Protocol

각 마일스톤을 구체화할 때 다음 역할을 수행/시뮬레이션해야 합니다:

- **`schema_guardian`**: `state.sqlite` 스키마 변경 시 `docs/specs/`와 동기화 무결성 방어.
- **`cli_regression_runner`**: 각 마일스톤 완료 후 `testbed/`에서 CLI 회귀 테스트 시나리오 실행.
- **`source_pair_analyst`**: 지식 정제 및 어노테이션 변경이 L1~L4 DAG에 미치는 영향 분석.

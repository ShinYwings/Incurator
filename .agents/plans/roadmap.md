# Incurator Master Roadmap

아키텍처 대공사를 위한 마스터 로드맵입니다. 각 마일스톤은 독립 브랜치로 작업하며, 구현 시작 전 `PLAN_TEMPLATE.md`를 따르는 상세 명세서를 별도 작성합니다.

**Global Priority Rule**: 작업 시작 전 반드시 `.agents/user_report.md`를 먼저 확인하세요. 미해결 항목이 있으면 그것부터 처리합니다.

---

## 📌 Milestones (우선순위 순)

### 1. Knowledge Sync Bridge ← 최우선
기기 간 지식(`state.sqlite`) 파편화 문제 해결. JSONL 기반 Export/Import 파이프라인과 Tombstone 충돌 해결 로직 구현. PDF Annotation 마일스톤의 전제 조건.

- `backend/src/curator/db_sync.py` 신규 구현
- `wiki db export / wiki db import` CLI 추가
- 기기 종속 데이터(임베딩 등) Export 블랙리스트 정책
- 연관 user_report 항목: 없음 (독립 인프라 마일스톤)
- 상세 명세: `knowledge_sync_bridge.md`

### 2. Minor Quick Wins
독립적인 소규모 개선 항목들. 백엔드 대공사와 무관하게 플러그인 단독 작업 가능. Knowledge Sync Bridge와 병행 또는 그 사이에 처리.

- **[마이너 업데이트] Diff Viewer UI/UX 개선**
- **[검증 필요] L1~L4 생성 문서 내 Obsidian `[[wikilink]]` 명시적 링킹 도입 여부 검토**
- **[마이너 업데이트] 웹 검색 기능 구현 검토**
- 상세 명세: `minor_quick_wins.md`

### 3. RAG & Knowledge Quality Stabilization
검색 품질과 지식 추출 정확도를 높입니다. FTS5 + Qwen3 Reranker 파이프라인 안정화, 수식 누락 문제 해결, 엔티티 중복 병합, GraphRAG급 군집화 도입. 가장 복잡한 Major 작업.

- 연관 user_report 항목: **검색 엔진 보완, 수식 누락 해결, LLM 설정 분리, GraphRAG 엔티티 통합, 계층적 군집화**
- 상세 명세: `stabilization.md`

### 4. Native PDF Annotation System
Zotero 의존성 제거. Knowledge Sync Bridge 완료 후 진행 (어노테이션도 기기 간 동기화 필요).

- `pdf_annotations` 테이블 설계
- 플러그인 하이라이팅 UI + IPC 연동
- Sync Bridge Export/Import 대상에 포함
- 연관 user_report 항목: 없음 (Sync Bridge 완료 후 추가 예정)
- 상세 명세: `pdf_annotation_system.md`

---

## 🤖 Multi-Agent Debate Protocol

각 마일스톤을 구체화할 때 다음 역할을 수행/시뮬레이션해야 합니다:

- **`schema_guardian`**: `state.sqlite` 스키마 변경 시 `docs/specs/`와 동기화 무결성 방어.
- **`cli_regression_runner`**: 각 마일스톤 완료 후 `testbed/`에서 CLI 회귀 테스트 시나리오 실행.
- **`source_pair_analyst`**: 지식 정제 및 어노테이션 변경이 L1~L4 DAG에 미치는 영향 분석.

---

## 📁 Evidence Ledger (사전 검증 장부)

이 섹션은 Stabilization, Sync Bridge, Native PDF Annotation 로드맵이 준수해야 할 사실적 기반을 기록합니다.
문서화, DB 마이그레이션, 플러그인 동작이 실제 레포지토리와 볼트의 상태에서 벗어나지 않도록 강제합니다.

### 1. Current Repository Reality
[To be filled by planning agents during deep research]
- Observed repository root:
- Current top-level layout:

### 2. Current Schema Reality To Recheck Before Migration
[To be filled by planning agents]
- Existing `sources`, `synthesis_nodes`, `knowledge_units` schema.
- Expected tombstone table (`deleted_records`) schema.

### 3. Current Dirty Worktree Categories
[To be filled immediately before executing codebase changes]
Because changes may belong to the user or another agent, no command may revert them casually.
Observed categories:
- 
- 

### 4. Known Validation Results From Current Work
[To be filled during Test-Driven Development]
- Backend tests passed:
- Plugin tests passed:
- Testbed verification:

### 5. Rollback Requirements Before Destructive Operations
[To be defined during planning]
- Git rollback anchors.
- Database (`.curator/state.sqlite`) backup steps.

### 6. Execution Updates (Phase-by-Phase)
[To be appended as each milestone executes]
- Knowledge Sync Bridge Update:
- RAG Stabilization Update:
- PDF Annotation Update:

# User Report

> **에이전트 참고**: 각 항목 옆 `→ plan` 링크가 해당 마일스톤 명세서입니다.
> 배치 작업 시 같은 plan에 묶인 항목들은 함께 처리하세요.



## 🚀 향후 해결할 미해결 항목 (To-Do)

### 📦 Knowledge Sync Bridge 마일스톤
- **[매이저 업데이트] Knowledge Sync Bridge 파이프라인 구현** 
  - 현상: 기기 간 지식(`state.sqlite`)이 파편화되는 문제를 해결하기 위해, JSONL 기반 Export/Import 및 Tombstone 충돌 해결(LWW) 로직이 필요함 (PDF Annotation 마일스톤의 전제 조건).
  - 요구사항: `wiki db export` / `wiki db import` CLI 추가, 기기 종속 데이터 필터링, 그리고 `deleted_records` 기반의 무손실 라운드트립 동기화 체계 구축.

#### 📋 마일스톤 상세 계획

Date: 2026-06-06
Status: APPROVED — implementing in phases. Specs are authored, tests are spec-first.

Domain Analysis:
- `A_sync_db_schema.md` — DB 스키마, Export 테이블 분류, JSONL 포맷, LWW 충돌 전략
- `B_sync_cli_interface.md` — CLI 명령어 설계, 모듈 구조, 기기 간 워크플로우

---

## Strict quality condition

- Export→Import→`wiki status` 라운드트립이 손실 없이 작동해야 함.
- `search_embeddings`, `ingest_jobs`, `job_events`는 어떤 경우에도 export 파일에 포함되지 않아야 함.
- schema_version 불일치 시 import는 명확한 오류와 함께 중단되어야 함 (silent 데이터 손상 금지).
- 기존 `wiki sync` (DAG 검증), `wiki reindex`, `wiki status` CLI 동작에 회귀 없어야 함.

---

## Locked design decisions

- **Tombstone 테이블**: `deleted_records(table_name, record_id, deleted_at)` 범용 단일 테이블. CHECK constraint로 허용 테이블명 제한. (A 문서 §1)
- **SCHEMA_VERSION**: 6 → 7 (non-destructive, `deleted_records` 테이블 추가만).
- **JSONL 포맷**: 단일 파일, 첫 줄 헤더, Tombstone 레코드 먼저. (A 문서 §3)
- **충돌 전략**: LWW (`updated_at` 기준). Tombstone > 수정 우선. (A 문서 §4)
- **CLI 구조**: `wiki db export/import` 신규 서브그룹. `wiki sync`는 DAG 검증 전용 유지. (B 문서 §1)
- **로직 분리**: `db_sync.py` 신규 모듈. `cli.py`는 얇은 래퍼만. (B 문서 §2)
- **Post-import**: `--skip-reindex` 없으면 자동 `wiki reindex` 실행. (B 문서 §1.2)

---

## Contracts preserved

- `wiki sync` 명령어 동작 변경 없음.
- `wiki reindex` 명령어 동작 변경 없음.
- `db.init_db(path)` 시그니처 유지. 내부에 v6→v7 마이그레이션 추가만.
- 기존 삭제 함수들(`delete_source` 등)의 반환값/시그니처 유지. 내부에 Tombstone INSERT 추가만.
- `SCHEMA_VERSION` 상수는 `db.py`에서만 관리.

---

## Multi-Agent Role Reviews

- **schema_guardian**: `deleted_records` 테이블 추가 시 `docs/specs/curator_schema/SCHEMA.md`에 v0.4.0으로 버전업 및 테이블 정의 동기화 필수. `SCHEMA_VERSION = 7` 변경도 스펙에 반영.
- **source_pair_analyst**: Export 중 `sources.logical_source_id` 기반 dedup이 Reference Mode 소스(Zotero 등)와 충돌하지 않는지 확인. `is_reference=1`인 소스의 `external_path`는 기기마다 다를 수 있으므로 Import 시 덮어쓰지 않도록 주의.
- **topic_boundary_checker**: Import된 레코드가 `02_Wiki/` 파일에 직접 쓰지 않음을 확인. DB 변경만으로 끝나고, 마크다운 파일 반영은 `wiki sync` 후속 단계.
- **cli_regression_runner**: `VAULT_ROOT=testbed wiki db export --out /tmp/test.jsonl` → `wiki db import /tmp/test.jsonl --dry-run` → `wiki status` 시퀀스를 testbed에서 스모크 테스트.
- **local_slm_simulator**: LLM 의존성 없음. 순수 SQLite I/O 작업이므로 LLM 블로커 무관.
- **legacy_sweeper**: `devices_app` (`wiki devices sync`)와 이름 충돌 없음. `db_app`은 별도 서브그룹.

---

## Phases

### P1 — DB Schema (Tombstone 테이블 + SCHEMA_VERSION bump)
- **구현**:
  - `db.py`: `SCHEMA_VERSION = 7`
  - `deleted_records` 테이블 + 인덱스 추가
  - `migrate_db()`: v6→v7 경로 추가 (ALTER TABLE 없이 CREATE TABLE IF NOT EXISTS)
  - 주요 삭제 함수에 Tombstone INSERT 추가 (`delete_source`, `delete_atom`, `delete_concept`, `delete_knowledge_unit`, `delete_graph_entity`, `delete_graph_relation`)
- **Verify**: `pytest tests/test_db.py -v` 통과 + `ruff check src/` 클린
- **Spec 업데이트**: `docs/specs/curator_schema/SCHEMA.md` — `deleted_records` 테이블 정의 추가, v0.4.0으로 버전업

### P2 — Core Export/Import Logic
- **구현**:
  - `backend/src/curator/db_sync.py` 신규 작성
  - `export_knowledge()`: JSONL 생성, 테이블 순서, 헤더 포맷
  - `import_knowledge()`: 헤더 검증, Tombstone 적용, LWW upsert, dry-run 지원
- **TDD**: `backend/tests/test_db_sync.py` 먼저 작성 (7개 케이스: B 문서 §4)
- **Verify**: `pytest tests/test_db_sync.py -v` 통과 + `ruff check src/`

### P3 — CLI Integration
- **구현**:
  - `cli.py`: `db_app` Typer 서브그룹 추가
  - `@db_app.command("export")`, `@db_app.command("import")` 구현
  - `--dry-run`, `--skip-reindex`, `--compress`, `--json`, `--since` 옵션
  - Post-import 자동 `wiki reindex` 연결
- **Verify**: `pytest tests/test_cli_db_sync.py -v` + `ruff check src/`

### P4 — Docs & Spec Update
- **구현**:
  - `docs/guides/USER_GUIDE.md` + `_KR.md`: `wiki db export/import` 섹션 추가
  - `docs/guides/WORKFLOW_GUIDE.md` + `_KR.md`: 기기 간 지식 이전 워크플로우 추가
  - `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`: DB Sync 동작 기술
- **Verify**: `pytest tests/test_spec_sync.py -v` 통과 (static spec 파일명 규칙 준수)

### P5 — Testbed Smoke & Full CI
- **구현**: testbed에서 E2E 라운드트립 검증
  ```bash
  VAULT_ROOT=testbed wiki db export --out /tmp/test_export.jsonl
  VAULT_ROOT=testbed wiki db import /tmp/test_export.jsonl --dry-run
  VAULT_ROOT=testbed wiki db import /tmp/test_export.jsonl
  VAULT_ROOT=testbed wiki status
  ```
- **Verify**: `pytest -q` (전체 백엔드 통과) + `ruff check src/` + `mypy src/`


### 📦 Minor Quick Wins 마일스톤
- **[마이너 업데이트] 웹 검색 기능 구현 검토** 
  - 현상: 로컬 모델(Ollama, Deepseek 등) 사용 시 웹 검색 기능 연동을 지원할지 설계 및 구현 필요.
- **[검증 필요] L1~L4 생성 문서 내 Obsidian `[[wikilink]]` 명시적 링킹 도입 여부 검토** 
  - 현상: 백엔드 파이프라인에서 생성되는 L1~L4 문서들에 핵심 엔티티나 개념이 옵시디언 고유의 `[[wikilink]]` 문법으로 명시화되어 있지 않음.
  - 불확실성(Pending): 사용자 기억상 과거 DB 구조에서 백링크(Backlink) 추적 시 정규식 편의를 위해 `()` 또는 일반 마크다운 링크를 쓰느라 `[[wikilink]]`를 의도적으로 제거했을 가능성이 있음.
  - 요구사항: 무작정 프롬프트를 고치기 전에, 기존 백엔드 DB의 파싱 로직(`()` 백링크 처리 등)과 `[[wikilink]]` 문법이 충돌하지 않는지 아키텍처 레벨에서 검증 후 도입 여부 결정.
- **[마이너 업데이트] Diff Viewer UI/UX 개선** 
  - 현황: `plugin/src/ui/diffViewer.ts` (530줄)에 기능 구현은 되어 있으나 현재 UI/UX가 불편함.
  - 요구사항: 사용자가 직관적으로 변경사항을 수락/거절할 수 있도록 UI/UX 전반 개선. 예: 버튼/헝크 레이아웃 정리, 다크/라이트 테마 대응, 키보드 단축키 힌트 표시, 헝크 간 이동 UX 등.

#### 📋 마일스톤 상세 계획

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


### 📦 RAG & Knowledge Quality Stabilization 마일스톤
- **[매이저 업데이트] 검색 엔진 심층 분석 및 보완** 
  - 현상: qmd가 어떻게 동작하는지 repository를 심층 분석해서 search engine에서 부족한 부분 보완.
- **[매이저 업데이트] PDF 및 정제된 지식(Atom, Concept) 내 수학 수식 누락 문제 해결** 
  - 현상: 현재 `pymupdf4llm`을 기본 파서로 사용 중이나, 표나 텍스트 흐름 보존과 달리 복잡한 공학/수학 논문의 블록 수식은 완벽한 `LaTeX` 코드로 역변환(OCR)되지 않고 깨지거나 누락되어 L1에 온전히 반영되지 않음. 또한, Markdown 원본에는 수식이 유지됨에도 불구하고, 이를 바탕으로 L2(Atom), L3(Concept)로 지식을 정제하는 과정에서 LLM이 수식을 보존하지 않고 증발시키는 문제가 있음.
  - 팩트체크 필요: 아키텍처 개편에 앞서, 실제로 `pymupdf4llm`이 수식 영역을 마크다운으로 변환할 때 어떤 형태의 텍스트(Garbage text)로 파편화하여 뱉어내는지, 혹은 완전히 생략해버리는지에 대해 L1 생성 결과물에 대한 구체적인 팩트체크 및 디버깅이 선행되어야 함.
  - 개선 방향 (하이브리드 파이프라인): 팩트체크 결과에 따라, 페이지 전체를 VLM에 넘기는 대신 `pymupdf4llm`으로 텍스트와 뼈대를 빠르게 잡고 수식(Formula)으로 판별된 영역만 이미지 캡처 후 백엔드 VLM(Claude, Gemini 등)에게 넘겨 `LaTeX` 코드로 번역하는 **하이브리드 추출 방식** 도입 검토. 아울러 LLM 지식 추출 프롬프트 자체도 수식을 보존하도록 강화 필수.
- **5. [매이저 업데이트] 지식 정제용 LLM과 쿼리 확장(HyDE)용 LLM 설정 분리 및 UI/CLI 노출** 
  - 현상: 사용자의 VRAM 환경과 용도(지식 정제용 무거운 모델 vs 쿼리 확장용 가볍고 빠른 로컬 모델)에 맞게 각각 독립적으로 모델을 선택할 수 있도록 설정 옵션을 명확히 제공해야 함.
  - 팩트체크 필요: 현재 백엔드 설정(`config.py`) 내부에 `query_expander` 관련 구조가 어느 정도 준비되어 있는지, 그리고 CLI(`wiki config provider`)와 플러그인 대시보드 UI에서 사용자가 이 두 모델을 직관적으로 따로 선택할 수 있도록 노출되어 있는지 팩트체크 및 검증 후 미비점 보완 필요.
- **6. [매이저 업데이트] GraphRAG급 엔티티 통합(Entity Resolution)(이게 적용되어도 되는건지 확인 필요), 노이즈 필터링 및 보관소 용량 관리(Vault Quota) 아키텍처 설계** 
  - 현상: 현재 자체 DB(`graph_entities`, `graph_relations`) 구조상 동의어나 유사 개념이 파편화되어 중복 저장되거나 노이즈 엣지가 무한 증식할 위험이 있음. `.curator` DB와 마크다운 파일들이 방치되면 컴퓨터 디스크 용량이 터질 수 있음.
  - 요구사항 1 (노이즈 필터링): 추출된 지식을 DB에 꽂아넣기 전/후로 임베딩 유사도 및 LLM을 활용해 동일한 엔티티를 병합하고 연결선 가중치를 정밀하게 최적화하는 파이프라인 아키텍처 설계 요망.
  - 요구사항 2 (용량 관리/Context Compat): 무한 증식을 막기 위해 보관소 최대 용량(Default: 200GB) 제한(Quota) 개념 도입.
  - 요구사항 3 (UI/UX 가시성): 사용자가 용량 압박을 직관적으로 인지할 수 있도록, **Claude Code 스타일의 원형 프로그레스 바(Circle Bar)** 형태의 UI를 도입. 
    - **옵시디언 에이전트**: 채팅창 상단에 상시 표시.
    - **CLI**: `wiki status` 출력 결과에 텍스트 대시보드 표시.
    - `wiki init` 시에도 명시적으로 용량 정책 안내 및 설정.
- **7. [매이저 업데이트] 전역적 사고(Global Sensemaking)를 위한 계층적 군집화 알고리즘 설계 플랜 작성** 
  - 현상: 수백 편의 논문 전체를 아우르는 거시적 통찰력(Global Summary)이나 커뮤니티 단위의 요약 기능이 부족함.
  - 요구사항: MS GraphRAG의 Leiden 알고리즘 등을 벤치마킹하여, 파편화된 L2(Atom) 지식들을 수학적으로 묶어 L3(Concept/Community) 단위로 자동 군집화하는 고도화된 클러스터링 로직 구현 플랜 작성 요망.

#### 📋 마일스톤 상세 계획

## Context
현재 RAG 검색 엔진(Qwen3 Reranker + FTS5)과 지식 추출(Distillation) 파이프라인에서 발생하는 할루시네이션, 엣지(Edge) 유실, 사전 지식(Prior Knowledge) 맵핑 불안정성을 해결해야 합니다. Knowledge Sync Bridge 및 PDF Annotation 개발에 앞서 기반을 닦는 핵심 과제입니다.

## Reference Plans (Must Read Before Implementation)
에이전트들은 다음 과거 아카이브 플랜들을 반드시 읽고, 기존 설계 의도와 RAG 구축 히스토리를 파악한 뒤 안정화에 돌입해야 합니다.
- `Git History (v0.3.2 search_internalization)`: (Qwen3 + FTS5 RAG 시스템 구축 히스토리)
- `Git History (2026-06-01_Generative_Backprop_Plan)`: (Generative Backprop 구조)
- `Git History (2026-06-01_Math_RAG_Backprop_Plan)`: (복잡한 수학/논리 백프롭 처리)

## Multi-Agent Debate Topics (For Codex & Claude)
1. **`schema_guardian`**: 
   - `search_documents`와 `knowledge_units` 간의 데이터 무결성을 검증하는 SQL 제약 조건을 어떻게 보완할 것인가?
2. **`source_pair_analyst`**: 
   - L3(Concepts) 및 L4(Synthesis) 레이어 생성 시, 원본 PDF Span(`source_spans`)으로의 역추적(Generative Backprop)이 끊어지는 버그의 원인은 무엇인가? 아카이브된 Backprop 플랜의 명세와 현재 구현체의 괴리를 어떻게 메울 것인가?
3. **`cli_regression_runner`**: 
   - `testbed` 스크립트를 통해 복잡한 RAG 질의 시 파이프라인 붕괴를 잡아낼 자동화 테스트를 어떻게 구성할 것인가?

## Implementation Skeleton
- `backend/src/curator/retrieval/*.py`: 과거 RAG 구축 플랜을 참조하여 Reranking 가중치 튜닝 및 하이브리드 서치 안정화.
- `backend/src/curator/pipeline/*.py`: L2->L3->L4 승격 로직의 프롬프트 및 유효성 검사 강화. (Generative Backprop 로직 정상화)
- `testbed`: `scripts/dev/`에 불안정성 및 Backprop 끊김 현상 재현을 위한 신규 시나리오 추가.


### 📦 Native PDF Annotation System 마일스톤
- **[매이저 업데이트] Native PDF Annotation System 도입 (Zotero 의존성 제거)** 
  - 현상: 외부 Zotero 시스템에 의존하던 PDF 하이라이팅 및 어노테이션을 자체 시스템으로 교체해야 함.
  - 요구사항: 옵시디언 내장 PDF Viewer를 활용하여 하이라이트와 메모를 `state.sqlite`(`pdf_annotations` 테이블)에 직접 저장하고 오프라인 동기화(Sync Bridge 연동)하며, Zotero 수준의 매끄러운 하이라이팅 UX 및 팝업 메모 UI를 구현.

#### 📋 마일스톤 상세 계획

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


## 🧊 Blocked / Icebox (대기 중인 보류 항목)
- 외부 의존성(라이브러리 업데이트 등) 문제로 당장 해결할 수 없는 항목들을 이곳에 보관합니다.
- (참고: 에이전트의 최우선 해결 의무(Global Priority Rule)에서 이 섹션의 항목들은 예외로 취급됩니다.)

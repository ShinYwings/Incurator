# Knowledge Sync Bridge — Master Implementation Plan

Date: 2026-06-06
Status: APPROVED — implementing in phases. Specs are authored, tests are spec-first.

Domain Analysis:
- `A_sync_db_schema.md` — DB 스키마, Export 테이블 분류, JSONL 포맷, LWW 충돌 전략
- `B_sync_cli_interface.md` — CLI 명령어 설계, 모듈 구조, 기기 간 워크플로우

---

## Linked user_report Items
이 마일스톤은 `user_report.md`의 다음 항목을 해결합니다:
- **[매이저 업데이트] Knowledge Sync Bridge 파이프라인 구현**

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

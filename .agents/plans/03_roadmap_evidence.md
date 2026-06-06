# Knowledge Sync Bridge — Evidence Ledger

Date: 2026-06-06
Status: PRE-IMPLEMENTATION (코딩 시작 직전 작성)

---

## 1. Rollback Requirements Before Destructive Operations

- Git 롤백 앵커: `release/v0.4.0` 브랜치, 현재 HEAD = `95fe2c1`
- P1은 non-destructive (테이블 추가만). `db.py` 변경 외 기존 파일 대규모 수정 없음.
- testbed가 있다면 `.curator/state.sqlite` 백업 권장. 없으면 `wiki testbed init` 후 진행.

## 2. Current Schema & Reality

- `SCHEMA_VERSION = 6` (db.py:23)
- `_apply_migrations()` 패턴: `_add_column_if_missing()` 호출로 idempotent 컬럼 추가.
- **기존 삭제 함수 없음**: `sources`, `atoms`, `concepts`, `graph_entities` 등 canonical 테이블에 DELETE 함수가 없음. Tombstone INSERT는 향후 삭제 연산 추가 시 적용. P1에서는 테이블 생성 + `record_tombstone()` 헬퍼만 작성.
- `init_db()` + `connect()` 모두 `_apply_migrations(conn)` 호출 → 마이그레이션은 여기 추가.
- FTS5 가상 테이블: `search_documents_fts`, `search_documents_fts_tri` — SCHEMA_SQL에 포함, JSONL 직렬화 불가 (확인).

## 3. Known Validation Results

### Pre-implementation baseline
- `pytest -q` 현재 결과: 확인 필요 (P1 전 실행)
- `ruff check src/`: 확인 필요

### Post-P1 목표
- `pytest tests/test_db.py -v`: 전체 통과
- `pytest tests/test_db_sync.py -v`: 신규 테스트 통과
- `ruff check src/`: 클린

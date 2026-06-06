# Knowledge Sync Bridge (DB Export/Import) Plan

## Context
기기 간 지식(`state.sqlite`) 파편화 문제를 해결하기 위해 오프라인 동기화 브릿지(JSONL)를 구축합니다.

## Multi-Agent Debate Topics (For Codex & Claude)
1. **`schema_guardian`**: 
   - `deleted_records` (Tombstone) 테이블 스키마를 어떻게 설계해야 하위 호환성을 유지하며 충돌을 방지할 수 있는가?
   - 임베딩 테이블 등 기기 종속적인 데이터를 확실하게 필터링할 `export` 블랙리스트 정책은?
2. **`source_pair_analyst`**: 
   - Timestamp 기반 병합(Merge) 시, 오프라인 상태에서 두 기기가 동시에 수정한 충돌(Conflict) 레코드는 어떻게 안전하게 병합할 것인가?
3. **`cli_regression_runner`**: 
   - 기기 A에서 Export 후 기기 B에서 Import 하고 `reindex`를 돌리는 전체 사이클을 자동 테스트할 스크립트 설계.

## Implementation Skeleton
- `backend/src/curator/db.py`: Tombstone 테이블 추가.
- `backend/src/curator/db_sync.py`: `export_knowledge()` 및 `import_knowledge()` 구현.
- `backend/src/curator/cli.py`: `wiki db export/import` 인터페이스 추가.

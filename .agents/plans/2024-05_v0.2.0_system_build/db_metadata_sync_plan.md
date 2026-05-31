# Plan: DB Metadata Sync (Future Refactoring)

Source: `.agents/plans/2024-05_v0.2.1_update/knowledge_verification_persistence_plan.md` Steps 1, 2, 5

## Problem

`state.sqlite`의 `atoms`, `concepts`, `synthesis` 테이블이 존재하지만 아무 코드도 쓰거나
읽지 않는다. Frontmatter가 진실의 원천이지만 DB와 동기화되지 않아 쿼리 기반 접근이 불가능하다.

## Scope

이 작업은 독립적인 리팩토링 태스크다. 모순 해결 워크플로우나 다른 기능 추가와 섞지 않는다.

## Steps

### 1. DB Helper Functions (`src/curator/db.py`)

```python
def upsert_atom_metadata(db_path, atom_id, data: dict) -> None
def upsert_concept_metadata(db_path, concept_id, data: dict) -> None
def upsert_synthesis_metadata(db_path, synthesis_id, data: dict) -> None
def get_node_status(db_path, node_id: str) -> dict | None
```

`data` 키: `is_flagged_for_agent`, `is_verified_by_human`, `confidence_score`, `last_updated`

### 2. Sync Pass (`src/curator/sync.py`)

`sync_metadata_to_db(paths)`: 4개 레이어 전체를 순회하며 frontmatter → DB 동기화.

`wiki sync` 마지막 단계에서 실행 (routing table rebuild 이후).

### 3. Verification Propagation (`src/curator/sync.py`)

`propagate_upstream_from_exhibition()` 이 Atom을 LLM으로 업데이트할 때,
상위 Exhibition이 `is_verified_by_human: true`이면 업데이트된 Atom에도 전파.

## Success Criteria

- `wiki sync` 완료 후 `state.sqlite`의 atoms 테이블에 `is_flagged_for_agent`, `confidence_score` 값 있음
- `curator_find_contradictions`가 DB를 옵션으로 사용 가능 (Frontmatter fallback 유지)
- `propagate_upstream_from_exhibition`이 전파 시 verification 플래그 옮김

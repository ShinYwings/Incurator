# [A] — DB Schema & Export/Import Design

Date: 2026-06-06
Status: DESIGN ARTIFACT (이 문서 작성 중에는 코드를 수정하지 않음)
Scope: `state.sqlite` JSONL 기반 Export/Import 파이프라인 — Tombstone 테이블 설계, 내보낼 테이블 목록 결정, 충돌 병합 전략.

---

## 0. Design constraints discovered from the codebase

- `db.py` SCHEMA_VERSION = 6. `schema_version` 테이블이 있으며 `init_db()`가 버전을 체크한다. Export 포맷에 schema_version을 포함해야 Import 측에서 호환성 검사를 할 수 있다.
- `state.sqlite`, `state.sqlite-wal`, `state.sqlite-shm`은 sync 도구가 직접 병합 불가라고 SCHEMA.md에 명시되어 있다. 이 기능이 그 공백을 채운다.
- `sources.relpath`는 vault root 상대 경로이므로, 기기마다 vault 위치가 달라도 relpath 기준으로 dedup할 수 있다.
- `sources.logical_source_id`는 경로/해시 드리프트에도 안정적인 소스 식별자 — Tombstone 기준키로 적합하다.
- 임베딩 BLOB(`search_embeddings.vector`)은 provider/model에 종속적이므로 절대 Export하면 안 된다.
- `ingest_jobs`, `job_events`는 워커 로컬 상태 — Export 제외.
- FTS5 가상 테이블(`search_documents_fts`, `search_documents_fts_tri`)은 SQLite 가상 테이블이라 JSONL로 직렬화 불가 — Import 후 `wiki reindex`로 재생성.

---

## 0.5 Docs Specs & Invariants

- **SCHEMA.md**: `state.sqlite` 변경 시 SCHEMA.md 업데이트 필수. 신규 `deleted_records` 테이블도 스펙에 추가해야 한다.
- **SYSTEM_BEHAVIOR.md**: `wiki db export / wiki db import` 동작을 System Behavior에 기술해야 한다.
- 기존 `SCHEMA_VERSION = 6` → Tombstone 테이블 추가 시 버전을 7로 올리고 마이그레이션 처리 필요.
- `03_Notes/`는 READ-ONLY — Export/Import가 DB 레코드만 다루고, vault 마크다운 파일을 건드려서는 안 된다. DB와 파일 동기화는 기존 `wiki sync`의 역할이다.

---

## 1. Tombstone Table

기기 A에서 삭제된 레코드를 기기 B가 Import할 때 적용하기 위한 삭제 기록 테이블.

### 1.1 Alternatives & Trade-offs

- **Option A: `deleted_records` 범용 테이블 (table_name + record_id)**
  - Pros: 단일 테이블로 모든 테이블의 삭제를 추적, 구현 단순.
  - Cons: FK 제약 없음 (SQLite에서 동적 FK는 불가능), 테이블명 오타 위험.

- **Option B: 테이블별 Tombstone (e.g., `deleted_sources`, `deleted_atoms`, …)**
  - Pros: 타입 안전, FK 가능.
  - Cons: 테이블 수가 많아 관리 복잡.

### 1.2 Decision: Option A (범용 Tombstone)

**결정 사항**: `deleted_records(table_name TEXT, record_id TEXT, deleted_at TEXT)` 단일 테이블 사용.
이유: 동기화 대상 테이블이 20+개이므로 범용이 현실적. `table_name` 컬럼은 CHECK constraint로 허용 테이블명 제한.

### 1.3 Implementation Logic

```sql
CREATE TABLE IF NOT EXISTS deleted_records (
    table_name  TEXT NOT NULL,
    record_id   TEXT NOT NULL,
    deleted_at  TEXT NOT NULL,
    PRIMARY KEY (table_name, record_id),
    CHECK (table_name IN (
        'sources','atoms','concepts','synthesis_nodes',
        'source_spans','knowledge_units','graph_entities','graph_relations',
        'community_reports','memory_paths','prompt_runs','dag_edges',
        'curation_plans','insight_candidates','artifact_dependencies',
        'synthesis','query_traces','source_pages','source_pdf_pages'
    ))
);
CREATE INDEX IF NOT EXISTS idx_deleted_records_at ON deleted_records(deleted_at);
```

삭제 트리거: `db.py`의 삭제 함수들(`delete_source`, etc.)에서 Tombstone INSERT 추가.

---

## 2. Export 대상 테이블 분류

### 2.1 Export 포함 (canonical, device-independent)

| 테이블 | 우선순위 | 비고 |
|--------|---------|------|
| sources | 필수 | 핵심 소스 메타데이터 |
| source_pages | 필수 | 소스↔페이지 프로버넌스 |
| source_pdf_pages | 필수 | PDF 페이지 단위 프로버넌스 |
| atoms | 필수 | L2 canonical |
| concepts | 필수 | L3 canonical |
| synthesis_nodes | 필수 | L4 canonical |
| source_spans | 필수 | 인용 단위 |
| knowledge_units | 필수 | 지식 그래프 |
| graph_entities | 필수 | 지식 그래프 |
| graph_relations | 필수 | 지식 그래프 |
| community_reports | 필수 | GraphRAG 요약 |
| dag_edges | 필수 | DAG 구조 |
| artifact_dependencies | 필수 | 스탤니스 추적 |
| curation_plans | 선택 | workspace 설정 |
| insight_candidates | 선택 | 리뷰 대기 |
| prompt_runs | 선택 | 실행 추적 (메타만, 벡터 없음) |
| query_traces | 선택 | 쿼리 기록 |
| memory_paths | 선택 | 연상 경로 |
| synthesis (legacy) | 선택 | 이전 L4 |
| deleted_records | 필수 | Tombstone — 삭제 전파용 |

### 2.2 Export 제외 (device-specific / transient)

| 테이블 | 제외 이유 |
|--------|---------|
| search_embeddings | provider/model 종속 벡터 BLOB |
| search_index_meta | 기기별 임베더 상태 |
| ingest_jobs | 워커 로컬 잡 상태 |
| job_events | 실시간 진행 로그 |
| page_hashes | 기기별 마지막 sync 타임스탬프 (재생성 가능) |
| search_documents | 파생 데이터 (reindex로 재생성) |
| search_chunks | 파생 데이터 |
| search_documents_fts | 가상 FTS5 테이블 (직렬화 불가) |
| search_documents_fts_tri | 가상 FTS5 테이블 (직렬화 불가) |
| schema_version | 메타데이터 (포맷 헤더로 별도 전달) |

---

## 3. JSONL Export 포맷

### 3.1 Alternatives & Trade-offs

- **Option A: 단일 JSONL 파일** (한 줄 = 한 레코드, `{"table": "...", "row": {...}}`)
  - Pros: 단순, streaming 처리 가능, gzip 친화적.
  - Cons: 테이블 순서가 중요할 때 파일 전체를 스캔해야 함.

- **Option B: 테이블별 JSONL 파일** (디렉터리)
  - Pros: 테이블 단위 병렬 처리 가능.
  - Cons: 파일 전송/공유 불편.

### 3.2 Decision: Option A (단일 JSONL)

**결정 사항**: 단일 `.jsonl` 파일. 첫 번째 줄은 메타 헤더.
이유: `scp`, `airdrop`, Syncthing 한 파일로 전달이 직관적. streaming parse로 메모리 효율적.

### 3.3 Implementation Logic

```
# 줄 1: 메타 헤더
{"type": "header", "schema_version": 6, "exported_at": "2026-06-06T12:00:00Z",
 "vault_id": "sha256-of-vault-root-relpath", "table_order": ["sources", "atoms", ...]}

# 이후: 각 레코드
{"type": "row", "table": "sources", "row": {"id": 1, "relpath": "...", ...}}
{"type": "row", "table": "atoms", "row": {"id": "ATM-abc123", ...}}
...
# Tombstone
{"type": "row", "table": "deleted_records", "row": {"table_name": "atoms", "record_id": "ATM-xyz", "deleted_at": "..."}}
```

---

## 4. Import & Conflict Resolution (LWW)

### 4.1 Alternatives & Trade-offs

- **Option A: Last-Write-Wins (LWW) by `updated_at` / `last_updated`**
  - Pros: 단순, 결정론적.
  - Cons: 시계 오차(NTP drift) 시 잘못된 버전이 이길 수 있음.

- **Option B: CRDT / Vector Clock**
  - Pros: 인과 순서 보장.
  - Cons: 구현 복잡, SQLite 스키마 대대적 변경 필요.

- **Option C: 수동 충돌 해결 (Conflict로 표시, 사용자 결정)**
  - Pros: 안전.
  - Cons: UX 번거로움, 배치 Import 시 블로킹.

### 4.2 Decision: Option A (LWW) + Tombstone 우선

**결정 사항**: LWW. `updated_at` / `last_updated` 기준으로 더 최신 레코드가 이긴다.
Tombstone 우선 규칙: Import 중 `deleted_records`에 레코드가 있으면, 로컬에 해당 레코드가 있어도 삭제한다. (삭제가 수정보다 우선)

```python
# 의사 코드
for record in jsonl_rows:
    if record["table"] == "deleted_records":
        apply_tombstone(record)  # 로컬 DB에서 해당 레코드 삭제 + Tombstone 추가
    else:
        local = db.get_by_id(record["table"], record["row"]["id"])
        if local is None:
            db.insert(record["table"], record["row"])
        elif record["row"].get("updated_at", "") > local.get("updated_at", ""):
            db.upsert(record["table"], record["row"])
        # else: local이 더 최신 → 무시
```

### 4.3 Post-Import

Import 완료 후 반드시 실행해야 하는 후처리:
1. `wiki reindex` — FTS5 + 임베딩 재생성 (search_documents, search_chunks, search_embeddings 재구축)
2. `wiki sync` — DAG 무결성 검증 (page_hashes 갱신, 깨진 링크 탐지)

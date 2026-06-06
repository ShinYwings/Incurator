# [B] — CLI Interface & Sync Workflow Design

Date: 2026-06-06
Status: DESIGN ARTIFACT (이 문서 작성 중에는 코드를 수정하지 않음)
Scope: `wiki db export / wiki db import` CLI 명령어 설계, 기기 간 전달 워크플로우, 사용자 경험.

---

## 0. Design constraints discovered from the codebase

- CLI는 `typer` 기반. 신규 서브그룹 추가 패턴: `db_app = typer.Typer(...)` → `app.add_typer(db_app, name="db")`.
- 기존 `wiki devices sync`는 Syncthing 설정 파일을 읽어 `.curator/devices.json`을 갱신하는 명령. 새 `wiki db export/import`와 이름 충돌 없음.
- `cli.py`는 4000줄+. 새 명령어는 별도 모듈 `db_sync.py`에 로직을 두고 CLI는 얇은 래퍼로 유지한다.
- `VAULT_ROOT` 환경변수로 vault를 선택 — 다중 vault 지원이 자연스럽게 된다.
- `wiki status`는 vault 상태를 출력 — Import 후 상태 확인 UX에 자연스럽게 연결됨.

---

## 0.5 Docs Specs & Invariants

- **USER_GUIDE.md**: `wiki db export / wiki db import` 사용법 추가 필수.
- **WORKFLOW_GUIDE.md**: 기기 간 지식 이전 워크플로우 섹션 추가 필수.
- 신규 CLI 명령은 testbed 스모크 테스트로 검증: `VAULT_ROOT=testbed wiki db export --out /tmp/test.jsonl`.
- `wiki db` 그룹은 사용자 직접 사용 명령이므로 `hidden=False`.

---

## 1. CLI Command Design

### 1.1 `wiki db export`

```
wiki db export [--out PATH] [--tables TABLE,...] [--since DATETIME]

Options:
  --out PATH           출력 파일 경로 (기본: .curator/export-YYYYMMDD.jsonl)
  --tables TEXT        특정 테이블만 export (기본: 전체 canonical 테이블)
  --since DATETIME     이 날짜 이후 변경된 레코드만 (증분 export)
  --compress           gzip 압축 (출력: .jsonl.gz)
  --json               머신 읽기용 JSON 출력 (plugin IPC용)
```

**동작**:
1. header row 작성 (schema_version, exported_at, vault_id)
2. `deleted_records` 테이블 먼저 export (Tombstone 우선 적용되도록)
3. canonical 테이블 순서대로 export
4. 완료 후 요약 출력 (테이블별 레코드 수)

### 1.2 `wiki db import`

```
wiki db import PATH [--dry-run] [--skip-reindex] [--json]

Arguments:
  PATH                 import할 .jsonl 또는 .jsonl.gz 파일

Options:
  --dry-run            실제 변경 없이 충돌/신규 레코드 수만 보고
  --skip-reindex       import 후 wiki reindex 자동 실행 건너뜀
  --json               머신 읽기용 JSON 출력
```

**동작**:
1. 헤더 검증 (schema_version 호환성 체크)
2. Dry-run이면 통계만 계산 후 종료
3. Tombstone 먼저 적용 (삭제 전파)
4. 나머지 레코드 LWW upsert
5. `--skip-reindex` 없으면 자동으로 `wiki reindex` 실행
6. 완료 요약 출력 (inserted, updated, skipped, deleted)

### 1.3 Alternatives & Trade-offs

- **Option A: `wiki db export/import` (별도 명령)**
  - Pros: 명확한 의도, 기존 `wiki sync`(DAG 검증)와 혼동 없음.
  - Cons: 사용자가 두 명령을 알아야 함.

- **Option B: `wiki sync --export/--import` 플래그 추가**
  - Pros: 단일 진입점.
  - Cons: `wiki sync`는 이미 DAG 검증 전용 — 책임 혼합, 기존 사용자 혼란.

### 1.4 Decision: Option A

`wiki db` 서브그룹 신설. `wiki sync`는 DAG 검증 전용으로 유지.

---

## 2. Module Structure

### 2.1 신규 파일: `backend/src/curator/db_sync.py`

```python
"""Cross-device SQLite knowledge synchronization via JSONL export/import."""

SYNC_TABLES: list[str] = [
    "deleted_records",  # 항상 첫번째
    "sources", "source_pages", "source_pdf_pages",
    "atoms", "concepts", "synthesis_nodes",
    "source_spans", "knowledge_units",
    "graph_entities", "graph_relations", "community_reports",
    "dag_edges", "artifact_dependencies",
    "curation_plans", "insight_candidates",
    "prompt_runs", "query_traces", "memory_paths",
    "synthesis",
]

EXCLUDE_TABLES: frozenset[str] = frozenset([
    "search_embeddings", "search_index_meta",
    "ingest_jobs", "job_events",
    "page_hashes",
    "search_documents", "search_chunks",
    "search_documents_fts", "search_documents_fts_tri",
    "schema_version",
])

def export_knowledge(db_path: Path, out_path: Path, ...) -> ExportStats: ...
def import_knowledge(db_path: Path, in_path: Path, dry_run: bool) -> ImportStats: ...
def _apply_tombstone(conn, table_name: str, record_id: str, deleted_at: str) -> None: ...
def _lw_upsert(conn, table_name: str, row: dict, updated_at_col: str) -> str: ...
    # returns: "inserted" | "updated" | "skipped"
```

### 2.2 `db.py` 변경

- `SCHEMA_VERSION = 6` → `7`
- `init_db()`: `deleted_records` 테이블 + 인덱스 추가
- `migrate_db()`: v6→v7 마이그레이션 (테이블 추가만이므로 non-destructive)
- 삭제 함수들에 Tombstone INSERT 추가:
  - `delete_source()`, `delete_atom()`, `delete_concept()` 등

### 2.3 `cli.py` 변경 (최소)

```python
db_app = typer.Typer(name="db", help="Knowledge database export and import.", ...)
app.add_typer(db_app, name="db")

@db_app.command("export")
def db_export(out: ..., tables: ..., since: ...) -> None:
    from curator.db_sync import export_knowledge
    stats = export_knowledge(paths.state_db, out_path, ...)
    ...

@db_app.command("import")
def db_import(path: Path, dry_run: bool, skip_reindex: bool) -> None:
    from curator.db_sync import import_knowledge
    stats = import_knowledge(paths.state_db, path, dry_run=dry_run)
    if not dry_run and not skip_reindex:
        _run_reindex(paths)
    ...
```

---

## 3. 기기 간 이전 워크플로우 (사용자 UX)

```
# 기기 A (출처)
VAULT_ROOT=~/second_brain wiki db export --out ~/Desktop/kb-sync.jsonl

# 파일 전송 (scp / airdrop / syncthing / usb)
scp ~/Desktop/kb-sync.jsonl user@machine-b:~/Desktop/

# 기기 B (대상)
VAULT_ROOT=~/second_brain wiki db import ~/Desktop/kb-sync.jsonl
# → 자동으로 wiki reindex 실행
# → 완료 요약 출력

VAULT_ROOT=~/second_brain wiki status  # 확인
```

---

## 4. 테스트 전략

- `test_db_sync.py`:
  - `test_export_creates_jsonl`: export 후 파일 존재, 헤더 포맷 검증.
  - `test_export_excludes_device_tables`: search_embeddings 등 미포함 확인.
  - `test_import_lw_wins`: A→B import 시 A의 최신 레코드가 반영됨.
  - `test_import_tombstone_deletes`: Tombstone이 B의 레코드를 삭제함.
  - `test_import_dry_run_no_changes`: dry-run 시 DB 변경 없음.
  - `test_round_trip`: export → fresh DB에 import → 레코드 동일성 검증.
  - `test_schema_version_mismatch`: 불호환 버전 파일 import 시 명확한 오류.

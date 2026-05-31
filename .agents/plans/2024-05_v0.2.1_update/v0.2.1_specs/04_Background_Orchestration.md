# 04. 백그라운드 오케스트레이션 및 상태 관리

본 명세서는 Obsidian 에이전트의 UI 블로킹을 원천 차단하기 위한 비동기 워커 아키텍처를
정의한다. 구버전 플랜의 "독립 daemon.py 프로세스" 방식은 폐기하고 MCP 서버 내장 워커
스레드로 대체한다.

---

## 1. 구버전 daemon.py 방식의 문제점

구버전 플랜은 별도의 `daemon.py` 프로세스를 띄우는 방식을 제안했다.

- **시작 시점 불명확**: `wiki daemon start`를 언제 누가 실행하나?
- **프로세스 관리 복잡**: MCP 서버 + daemon 두 프로세스를 동시에 관리
- **크래시 복구 없음**: `running` 상태에서 죽으면 작업이 영구 stuck
- **Windows 비호환**: systemd 없는 환경에서 자동 시작 불가

---

## 2. 올바른 아키텍처: MCP 서버 내장 `IngestWorker` 스레드

```python
# backend/src/curator/ingest_worker.py

import threading

class IngestWorker(threading.Thread):
    """MCP 서버 시작 시 자동으로 함께 시작되는 백그라운드 워커"""

    def __init__(self, db_path: str, vault_root: str):
        super().__init__(daemon=True)  # 메인 프로세스 종료 시 자동 종료
        self.db_path = db_path
        self.vault_root = vault_root
        self._stop = threading.Event()

    def run(self):
        self._recover_stale_jobs()   # 시작 시 크래시 복구
        while not self._stop.is_set():
            job = self._claim_next_job()
            if job:
                self._process_job(job)
            else:
                self._stop.wait(timeout=10)  # 작업 없으면 10초 대기

    def _recover_stale_jobs(self):
        """이전 크래시로 stuck된 running 작업을 queued로 되돌림"""
        with db.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE ingest_jobs SET state='queued', error=NULL "
                "WHERE state='running'"
            )

    def _claim_next_job(self) -> dict | None:
        """원자적 claim: SELECT + UPDATE를 한 트랜잭션으로"""
        with db.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM ingest_jobs WHERE state='queued' "
                "ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE ingest_jobs SET state='running', started_at=? WHERE id=?",
                (now_iso(), row["id"])
            )
            return dict(row)

    def _process_job(self, job: dict):
        try:
            if job["job_type"] == "l2_atoms":
                run_pass1_atoms(job["source_id"], self.vault_root)
            elif job["job_type"] == "l3_concepts":
                run_pass2_concepts(job["source_id"], self.vault_root)
            elif job["job_type"] == "l4_exhibitions":
                run_pass3_exhibitions(job["source_id"], self.vault_root)

            db.mark_job_done(self.db_path, job["id"])
            # 다음 단계 자동 큐잉
            _enqueue_next_phase(self.db_path, job)

        except Exception as e:
            db.mark_job_failed(self.db_path, job["id"], str(e))
```

### 2.1. MCP 서버 시작 시 자동 구동

```python
# mcp_server.py

worker = IngestWorker(db_path=str(db_path), vault_root=str(vault_root))
worker.start()  # MCP 서버 초기화 시 함께 시작, 별도 명령 불필요
```

---

## 3. `wiki add` vs `wiki curate` — 레이어 분리 원칙

**`wiki add` = L1-L3 담당, `wiki curate` = L4 담당.**

이것은 v0.2.0부터 확립된 설계 원칙이다 (`ingest_llm.py:1996` 주석 참조).

```
wiki add paper.pdf
  1. PyMuPDF로 L1 파싱 (빠름, 즉각 실행)
  2. CTX-UUID.md 생성, DB sources 등록
  3. ingest_jobs에 l2_atoms 작업 등록 (state=queued)
  4. 즉시 반환: "L1 등록 완료. L2~L3는 백그라운드 처리 중."

→ IngestWorker가 백그라운드에서 처리 (L3까지만):
   l2_atoms → (완료 후 자동) l3_concepts → 완료

wiki curate  ← L4 Exhibition은 이 명령에서만 생성
  1. workspace의 curate.yml(Knowledge Requirement Spec) 읽기
  2. 각 required_topic에 맞는 L3 Concept 검색
  3. Exhibition 생성 (generation_trigger='wiki_curate')
  4. L4는 워크스페이스 맥락(curate.yml)이 있어야 의미있으므로 자동 체인 불가
```

**왜 L4를 `wiki add` 체인에 넣지 않는가:**
- Exhibition은 curate.yml의 Knowledge Requirement Spec을 기반으로 만들어진다
- 문서를 add할 때마다 자동 생성하면 spec 없이 의미없는 Exhibition이 남발됨
- `wiki curate`는 명시적 사용자 의도(curate.yml 작성)가 전제됨
- 추가로, `curator_query()` MCP 도구도 온디맨드로 Exhibition을 생성한다 (spec 07)

각 단계 내부의 병렬 처리는 IngestOrchestrator가 담당.
spec 08(Performance_SubAgent_Architecture) 참조:
- `l2_atoms` 잡 → IngestOrchestrator.run_l2_parallel()
- `l3_concepts` 잡 → IngestOrchestrator.run_l3_parallel()

IngestWorker는 "L1-L3 잡 큐 처리자"이고, IngestOrchestrator는 "단일 잡 내부 병렬 처리자"다.

---

## 3.5. Staging 디렉토리

IngestOrchestrator의 병렬 worker들은 최종 Collections/ 경로가 아닌 **staging 디렉토리**에
파일을 먼저 기록한다. 모든 worker가 완료된 후 Orchestrator 메인 스레드가 staging → Collections/
로 atomic 복사하고 DB를 일괄 커밋한다. 이렇게 하면 부분 완료 상태의 노드 파일이 없다.

```text
.curator/staging/          ← IngestOrchestrator 병렬 worker 임시 기록 공간
.curator/Collections/      ← worker 완료 후 atomic 복사 대상 (최종 상태)
```

staging 경로:

```python
staging: Path = paths.curator_dir / "staging"
staging.mkdir(parents=True, exist_ok=True)  # 없으면 자동 생성

# 파일명 규칙 (worker 간 충돌 방지)
staged_path = staging / f"02_Atoms__{atom_id}.md"    # L2 atom
staged_path = staging / f"03_Concepts__{con_id}.md"  # L3 concept
staged_path = staging / f"04_Exhibitions__{exh_id}.md"
```

staging 디렉토리는 `.stignore`(Syncthing)와 `.gitignore`에 포함되어 동기화·버전관리 대상에서
제외된다.

---

## 4. DB 스키마

### 4.1. `ingest_jobs` 테이블

```sql
CREATE TABLE IF NOT EXISTS ingest_jobs (
    id               TEXT PRIMARY KEY,
    source_id        TEXT NOT NULL REFERENCES sources(id),
    job_type         TEXT NOT NULL,
    -- l2_atoms | l3_concepts | l4_exhibitions | l4_query
    -- rebuild_atom | rebuild_concept          ← spec 05 backprop 재빌드용
    state            TEXT NOT NULL DEFAULT 'queued',
    -- queued | running | done | failed
    created_at       TEXT NOT NULL,
    started_at       TEXT,
    finished_at      TEXT,
    error            TEXT,
    input_tokens     INTEGER DEFAULT 0,
    output_tokens    INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0.0,
    trigger          TEXT DEFAULT 'wiki_add',  -- wiki_add | mcp_query | backprop
    progress_current INTEGER DEFAULT 0,        -- spec 09 dashboard 진행률 표시용
    progress_total   INTEGER DEFAULT 0,
    source_name      TEXT DEFAULT ''           -- 파일명 (display용)
);
```

IngestWorker `_process_job()` 는 모든 job_type을 처리해야 한다:

```python
def _process_job(self, job: dict):
    try:
        jt = job["job_type"]
        if jt == "l2_atoms":
            IngestOrchestrator(self.paths, self.config).run_l2_batch(
                job["source_id"], self.staging, today_iso()
            )
        elif jt == "l3_concepts":
            IngestOrchestrator(self.paths, self.config).run_l3_parallel(
                job["source_id"], self.staging, today_iso()
            )
        elif jt in ("rebuild_atom", "rebuild_concept"):
            # spec 05 backprop 재빌드 — 단일 노드 재생성
            IngestOrchestrator(self.paths, self.config).rebuild_node(
                node_id=job["node_id"],    # backprop enqueue 시 추가 필드
                job_type=jt,
                staging=self.staging,
                today=today_iso(),
            )
        elif jt == "l4_exhibitions":
            # backprop 재빌드만 해당 (wiki curate 정규 경로와 무관)
            IngestOrchestrator(self.paths, self.config).run_l4_parallel(
                [job["node_id"]], self.staging, today_iso()
            )

        db.mark_job_done(self.db_path, job["id"])
        _enqueue_next_phase(self.db_path, job)
        self._write_dashboard()

    except Exception as e:
        db.mark_job_failed(self.db_path, job["id"], str(e))
        self._write_dashboard()
```

### 4.2. `dag_edges` 테이블

DAG 관계를 파일 스캔 없이 SQL로 조회하기 위한 테이블.
spec 08(incremental sync), spec 05(backprop forward/backward pass),
spec 09(Canvas 생성)이 모두 이 테이블에 의존한다.

```sql
CREATE TABLE IF NOT EXISTS dag_edges (
    id          TEXT PRIMARY KEY,   -- '{from_id}:{to_id}'
    from_id     TEXT NOT NULL,      -- CTX-xxx | ATM-xxx | CON-xxx
    to_id       TEXT NOT NULL,      -- ATM-xxx | CON-xxx | EXH-xxx
    edge_type   TEXT NOT NULL,
    -- 'extracted_from'  : CTX → ATM  (L1에서 L2 추출)
    -- 'clustered_to'    : ATM → CON  (L2 → L3 클러스터링)
    -- 'synthesized_to'  : CON → EXH  (L3 → L4 합성)
    source_id   TEXT REFERENCES sources(id),
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dag_edges_from ON dag_edges(from_id);
CREATE INDEX IF NOT EXISTS idx_dag_edges_to   ON dag_edges(to_id);
```

IngestOrchestrator가 각 레이어 완료 직후 즉시 기록 (spec 09 섹션 1 참조).

---

## 5. `wiki status` 백그라운드 작업 표시

```
$ wiki status

Vault: /home/shin/Workspace/second_brain
Sources: 15 (12 complete, 2 processing, 1 queued)

Background jobs:
  [==========-] paper_xyz.pdf  l2_atoms   running  (23/47 sections)
  [queued]      new_paper.pdf  l2_atoms   waiting

LLM cost to date: $2.43  (input 1.2M + output 340K tokens)
```

`check_ingest_status` MCP 툴도 같은 정보 반환 → Obsidian 사이드바 진행률 표시.

---

## 6. SQLite WAL + 동시성 안전성

- `db.py`의 WAL 모드(`PRAGMA journal_mode=WAL`)는 이미 활성화됨
- MCP 서버(읽기 다수) + IngestWorker(쓰기 단일) 구조 → WAL이 완벽히 커버
- L3 Concept 클러스터링은 크로스 소스 → 글로벌 병합 단계에서 단일 트랜잭션으로 처리

```python
# 글로벌 병합 시 트랜잭션 사용
with db.connect(db_path) as conn:
    conn.execute("BEGIN EXCLUSIVE")  # 쓰기 락
    for draft in concept_drafts:
        merge_or_create_concept(conn, draft)
    conn.execute("COMMIT")
```

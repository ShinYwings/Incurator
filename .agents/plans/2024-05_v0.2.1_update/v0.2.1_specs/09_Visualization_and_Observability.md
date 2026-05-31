# 09. 가시성(Observability) 및 빌드 트레이스 시각화

Incurator는 3개 경계에서 "무슨 일이 일어나고 있는지"를 사용자에게 보여줘야 한다.
현재는 모든 처리가 블랙박스로 진행되며, 사용자는 완료 메시지만 받는다.

```
관찰 경계 1: 백그라운드 IngestWorker 진행 상황
             (wiki add 후 몇 분간 L2/L3가 조용히 처리 중)

관찰 경계 2: 지식 정제 구조
             (ATM이 어떤 CON으로 클러스터링됐는지, DAG가 어떻게 생겼는지)

관찰 경계 3: 에이전트 쿼리 경로
             (curator_query가 어떤 노드를 거쳐 어떤 EXH를 반환했는지)
```

목표 UX: Ask Gemini 사이드바처럼, 답변과 함께 "어디서 왔는지"를 투명하게 보여줌.

---

## 1. Observability Foundation: SQLite dag_edges 테이블

모든 시각화 레이어의 공통 기반 인프라. spec 08 섹션 9.3에서도 참조.

파일 시스템 스캔 없이 DAG 구조를 SQL로 조회하려면
`state.sqlite`에 edges 테이블이 필요하다.

```sql
-- db.py에 추가 (기존 ingest_jobs 테이블과 동일 파일)
CREATE TABLE IF NOT EXISTS dag_edges (
    id          TEXT PRIMARY KEY,   -- '{from_id}:{to_id}'
    from_id     TEXT NOT NULL,      -- CTX-xxx | ATM-xxx | CON-xxx
    to_id       TEXT NOT NULL,      -- ATM-xxx | CON-xxx | EXH-xxx
    edge_type   TEXT NOT NULL,      -- 'extracted_from' | 'clustered_to' | 'synthesized_to'
    source_id   TEXT REFERENCES sources(id),
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dag_edges_from ON dag_edges(from_id);
CREATE INDEX IF NOT EXISTS idx_dag_edges_to   ON dag_edges(to_id);
```

```python
# db.py — 새 helper

def insert_dag_edge(db_path: str, from_id: str, to_id: str,
                    edge_type: str, source_id: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO dag_edges (id, from_id, to_id, edge_type, source_id, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (f"{from_id}:{to_id}", from_id, to_id, edge_type, source_id, now_iso()),
        )

def get_dag_edges_for_source(db_path: str, source_id: str) -> list[dict]:
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(
            "SELECT from_id, to_id, edge_type FROM dag_edges WHERE source_id=?",
            (source_id,),
        ).fetchall()]
```

**기록 시점**: IngestOrchestrator가 각 레이어 완료 직후 즉시 기록.
별도 sync pass 불필요.

```python
# ingest_orchestrator.py — run_l2_batch() 완료 후
for atom_id in created_atom_ids:
    db.insert_dag_edge(paths.state_db,
                       from_id=context_id, to_id=atom_id,
                       edge_type="extracted_from", source_id=source_id)

# run_l3_parallel() 완료 후
for concept_id, atom_cluster in concept_clusters.items():
    for atom_id in atom_cluster:
        db.insert_dag_edge(paths.state_db,
                           from_id=atom_id, to_id=concept_id,
                           edge_type="clustered_to", source_id=source_id)

# wiki curate run_l4_parallel() 완료 후
for exh_id, concept_ids in exh_sources.items():
    for concept_id in concept_ids:
        db.insert_dag_edge(paths.state_db,
                           from_id=concept_id, to_id=exh_id,
                           edge_type="synthesized_to", source_id=None)
```

---

## 2. ingest_jobs 테이블 확장

spec 04에서 정의된 `ingest_jobs` 테이블에 진행률 필드 추가:

```sql
ALTER TABLE ingest_jobs ADD COLUMN progress_current INTEGER DEFAULT 0;
ALTER TABLE ingest_jobs ADD COLUMN progress_total   INTEGER DEFAULT 0;
ALTER TABLE ingest_jobs ADD COLUMN source_name      TEXT DEFAULT '';
-- source_name: 파일명 (display용, "paper_xyz.pdf" 등)
```

IngestWorker가 작업 중 주기적으로 갱신:

```python
# L2 batch extraction — 모든 atom이 staging에 쓰인 후
db.update_job_progress(db_path, job_id,
                       current=len(staged_atoms),
                       total=len(staged_atoms))

# L3 — concept 하나 완료될 때마다
db.update_job_progress(db_path, job_id, current=done_count, total=total_count)
```

---

## 3. 레이어 1: 백그라운드 작업 진행률

### 3.1. `.curator/dashboard.md` (파일 기반 — 추가 플러그인 코드 없음)

IngestWorker가 job 상태 변경마다 이 파일을 덮어쓴다.
Obsidian live preview가 파일 변경을 감지하여 자동 재렌더링한다.
추가 플러그인 소켓/폴링 코드 불필요.

```python
# ingest_worker.py — _write_dashboard()

def _write_dashboard(self):
    running = db.get_jobs_by_state(self.db_path, "running")
    queued  = db.get_jobs_by_state(self.db_path, "queued")
    done_today = db.get_jobs_done_today(self.db_path)
    cost = db.get_total_cost(self.db_path)

    lines = [
        "# Incurator Build Status",
        f"*{now_iso()}*",
        "",
    ]

    if running:
        lines += ["## Active", "| Source | Phase | Progress |",
                  "|--------|-------|----------|"]
        for job in running:
            prog = (f"{job['progress_current']}/{job['progress_total']}"
                    if job["progress_total"] else "…")
            lines.append(f"| {job['source_name']} | {job['job_type']} | {prog} |")
    else:
        lines.append("## Active — idle")

    if queued:
        lines += ["", "## Queue",
                  "| Source | Phase |", "|--------|-------|"]
        for job in queued:
            lines.append(f"| {job['source_name']} | {job['job_type']} |")

    if done_today:
        total_atoms = sum(j.get("atoms_created", 0) for j in done_today)
        total_concepts = sum(j.get("concepts_created", 0) for j in done_today)
        lines += [
            "",
            "## Completed Today",
            f"{len(done_today)} jobs · {total_atoms} atoms · {total_concepts} concepts",
            f"Cost: ${cost:.3f}",
        ]

    dashboard_path = Path(self.vault_root) / ".curator" / "dashboard.md"
    # 원자적 write (partial read 방지)
    tmp = dashboard_path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(dashboard_path)
```

호출 시점: `_process_job()` 시작 전, 완료 후, 실패 후.

```
.curator/dashboard.md (렌더 예시)

# Incurator Build Status
*2026-05-29T14:32:07Z*

## Active
| Source         | Phase     | Progress |
|----------------|-----------|----------|
| paper_xyz.pdf  | l3_concepts | 3/5    |

## Queue
| Source         | Phase    |
|----------------|----------|
| new_paper.pdf  | l2_atoms |

## Completed Today
2 jobs · 47 atoms · 8 concepts
Cost: $0.043
```

### 3.2. Plugin Status Bar

`check_ingest_status()` MCP 툴 (spec 04에서 이미 정의)을 5초 간격으로 폴링.
Obsidian status bar 오른쪽에 표시:

```
상태별 표시:
  ⚡ 2 running / 1 queued    ← 진행 중
  ✓ All synced               ← idle
  ✗ 1 failed                 ← 실패 (클릭 → dashboard.md 오픈)
```

클릭 이벤트: `.curator/dashboard.md`를 Obsidian에서 오픈.

플러그인 구현은 `plugin/src/utils/incuratorBackendStatus.ts`에서 처리
(이미 파일이 존재함 — MCP 상태 polling 로직 포함 예정).

---

## 4. 레이어 2: 지식 정제 구조 시각화 (Obsidian Canvas)

### 4.1. Canvas 자동 생성

IngestWorker가 `l3_concepts` 잡 완료 후 source별 Canvas 파일 생성:
`.curator/build_trace_{source_slug}.canvas`

Obsidian Canvas는 `.canvas` JSON 파일을 native로 렌더링한다.
추가 플러그인 없이 노드/엣지 그래프를 볼 수 있다.

```python
# ingest_worker.py — _write_build_canvas()

def _write_build_canvas(self, source_id: str, source_slug: str):
    """L3 완료 후 ATM → CON 클러스터 구조를 Canvas JSON으로 저장."""
    edges = db.get_dag_edges_for_source(self.db_path, source_id)

    # 노드 ID 집합 수집
    ctx_ids, atm_ids, con_ids, exh_ids = set(), set(), set(), set()
    for e in edges:
        _classify(e["from_id"], ctx_ids, atm_ids, con_ids, exh_ids)
        _classify(e["to_id"],   ctx_ids, atm_ids, con_ids, exh_ids)

    # Canvas 노드 배치 (레이어별 x 좌표, 순서별 y 좌표)
    nodes = []
    LAYER_X = {"CTX": 0, "ATM": 320, "CON": 640, "EXH": 960}
    COLORS  = {"CTX": "1", "ATM": "3", "CON": "4", "EXH": "6"}
    # blue=1, red=2, yellow=3, green=4, cyan=5, purple=6

    for i, nid in enumerate(sorted(ctx_ids)):
        nodes.append(_canvas_node(nid, "01_Contexts", LAYER_X["CTX"], i*90, COLORS["CTX"]))
    for i, nid in enumerate(sorted(atm_ids)):
        nodes.append(_canvas_node(nid, "02_Atoms",    LAYER_X["ATM"], i*90, COLORS["ATM"]))
    for i, nid in enumerate(sorted(con_ids)):
        nodes.append(_canvas_node(nid, "03_Concepts", LAYER_X["CON"], i*150, COLORS["CON"]))
    for i, nid in enumerate(sorted(exh_ids)):
        nodes.append(_canvas_node(nid, "04_Exhibitions", LAYER_X["EXH"], i*150, COLORS["EXH"]))

    canvas_edges = [
        {
            "id": f"e_{e['from_id']}_{e['to_id']}",
            "fromNode": e["from_id"], "toNode": e["to_id"],
            "label": e["edge_type"],
        }
        for e in edges
    ]

    canvas = {"nodes": nodes, "edges": canvas_edges}
    out_path = (Path(self.vault_root) / ".curator"
                / f"build_trace_{source_slug}.canvas")
    out_path.write_text(json.dumps(canvas, indent=2, ensure_ascii=False),
                        encoding="utf-8")


def _canvas_node(node_id: str, layer_subdir: str, x: int, y: int, color: str) -> dict:
    return {
        "id": node_id,
        "type": "file",
        "file": f".curator/Collections/{layer_subdir}/{node_id}.md",
        "x": x, "y": y, "width": 220, "height": 60,
        "color": color,
    }

def _classify(nid, ctx_s, atm_s, con_s, exh_s):
    if nid.startswith("CTX-"): ctx_s.add(nid)
    elif nid.startswith("ATM-"): atm_s.add(nid)
    elif nid.startswith("CON-"): con_s.add(nid)
    elif nid.startswith("EXH-"): exh_s.add(nid)
```

렌더 결과:

```
[CTX-abc]  →  [ATM-001]  →  [CON-xyz]
           →  [ATM-002]  ↗
           →  [ATM-003]  →  [CON-pqr]
           →  [ATM-004]  ↗
```

노드를 클릭하면 해당 `.md` 파일이 Obsidian에서 열린다.

### 4.2. SyncCallbacks 확장 (기존 인프라 활용)

`sync.py`에는 이미 `SyncCallbacks` 클래스가 존재한다:

```python
class SyncCallbacks:
    def on_node_check(self, node_id: str): pass
    def on_node_repair(self, node_id: str, rebuilt_count: int = 0, ...): pass
```

이 hook을 활용하여 sync 진행 중 dashboard.md를 업데이트:

```python
# sync.py — 신규 구현체

class DashboardSyncCallbacks(SyncCallbacks):
    def __init__(self, dashboard_path: Path, total_nodes: int):
        self.dashboard_path = dashboard_path
        self.total = total_nodes
        self.checked = 0
        self.repaired = 0

    def on_node_check(self, node_id: str):
        self.checked += 1
        if self.checked % 20 == 0:   # 20개마다 갱신 (과도한 I/O 방지)
            self._patch_dashboard(f"Syncing: {self.checked}/{self.total}")

    def on_node_repair(self, node_id: str, rebuilt_count: int = 0, **_):
        self.repaired += 1
        self._patch_dashboard(
            f"Repairing: {node_id} (+{rebuilt_count} rebuilt)"
        )

    def _patch_dashboard(self, status_line: str):
        # dashboard.md의 "Sync" 섹션만 교체 (전체 덮어쓰기 대신)
        ...
```

`wiki sync` 실행 시 자동으로 `DashboardSyncCallbacks` 인스턴스를 생성하여 전달.

---

## 5. 레이어 3: 에이전트 쿼리 트레이스

### 5.1. `curator_query()` 응답에 `trace` 필드 추가

spec 07의 `curator_query()` 반환값에 trace 정보를 포함:

```python
def curator_query(
    question: str,
    workspace_id: str,
    force_new: bool = False,
) -> dict:
    t0 = time.monotonic()
    trace = {"query": question}

    # Step 1: L3 Concept 검색
    relevant_concepts = search_concepts(question, top_k=5)
    trace["matched_concepts"] = [
        {"id": c.id, "title": c.title, "score": round(c.score, 3)}
        for c in relevant_concepts
    ]
    concept_ids = [c.id for c in relevant_concepts]

    # Step 2: EXH 캐시 확인 (spec 07)
    cached = find_cached_exhibition(concept_ids, workspace_id) if not force_new else None
    if cached:
        trace["exhibition_id"] = cached.id
        trace["cache_hit"] = True
        exh = cached
    else:
        # Step 3: 신규 EXH 생성
        exh = generate_exhibition_from_concepts(
            concept_ids=concept_ids,
            generation_query=question,
            workspace_id=workspace_id,
        )
        save_exhibition(exh)
        trace["exhibition_id"] = exh.id
        trace["cache_hit"] = False

    trace["latency_ms"] = int((time.monotonic() - t0) * 1000)
    return {"exhibition": exh, "trace": trace}
```

반환 예시:

```json
{
  "exhibition": { "id": "EXH-abc", "content": "..." },
  "trace": {
    "query": "What is self-attention?",
    "matched_concepts": [
      { "id": "CON-abc", "title": "Self-Attention Mechanism", "score": 0.912 },
      { "id": "CON-def", "title": "Positional Encoding",     "score": 0.784 },
      { "id": "CON-ghi", "title": "Feed-Forward Sublayer",   "score": 0.631 }
    ],
    "exhibition_id": "EXH-xyz",
    "cache_hit": true,
    "latency_ms": 340
  }
}
```

### 5.2. Plugin Sidebar "Sources & Trace" 패널

`plugin/src/ui/` 내 Incurator 사이드 패널 하단에 접을 수 있는 섹션.
답변이 렌더링된 후 trace 데이터로 채워진다.

```
┌─ Incurator ──────────────────────────────────────┐
│                                                   │
│  [질문에 대한 EXH 내용 렌더링]                      │
│  ...                                              │
│                                                   │
│  ▼ Sources & Trace  (340ms)                       │
│  ┌─────────────────────────────────────────────┐  │
│  │ ● CON-abc  Self-Attention Mechanism   0.91  │  │
│  │ ● CON-def  Positional Encoding        0.78  │  │
│  │ ○ CON-ghi  Feed-Forward Sublayer      0.63  │  │
│  │                                             │  │
│  │ Exhibition: EXH-xyz  [cache hit ✓]          │  │
│  │ [Open in Obsidian ↗]                        │  │
│  └─────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────┘
```

`● / ○` 기호: 0.75 이상이면 ●(strong match), 이하면 ○(weak match).
`[Open in Obsidian ↗]`: `obsidian://open?vault=...&file=...` URI로 해당 EXH 파일 오픈.

구현 파일: `plugin/src/ui/incuratorQueryTrace.ts` (신규).
`externalPdfView.ts` 또는 독립 사이드뷰에서 import하여 사용.

---

## 6. 이전 플랜과의 통합

### 6.1. db_metadata_sync_plan.md

`.agents/plans/2024-05_v0.2.0_system_build/db_metadata_sync_plan.md`에서 계획된 `sync_metadata_to_db()`:

> `wiki sync` 마지막 단계에서 frontmatter → DB 동기화 실행

본 spec에서는 이를 **ingest 파이프라인의 즉시 기록**으로 격상한다:
- `sync_metadata_to_db()` 별도 pass 대신, IngestOrchestrator가 노드 생성 시 즉시 DB 기록
- dag_edges + `atoms`/`concepts`/`synthesis` 테이블이 항상 최신 상태 유지
- `wiki sync`가 끝날 때까지 기다리지 않아도 대시보드가 real-time 정보를 보여줌

db_metadata_sync_plan의 `upsert_atom_metadata()` / `upsert_concept_metadata()` helper 함수들은
인프라로서 그대로 유지하고, 호출 시점만 sync pass → ingest 시 즉시로 변경.

### 6.2. orchestrated_pipeline_and_persona_system.md

`.agents/plans/2024-04_pipeline_and_persona/orchestrated_pipeline_and_persona_system.md`의 Phase 3에서
`SyncCallbacks` 클래스와 `sync.py` Mode C `ThreadPoolExecutor`가 이미 구현되어 있다.

본 spec의 `DashboardSyncCallbacks`는 이 기존 인프라를 확장하는 것이므로
`sync.py`를 크게 수정할 필요 없이 콜백 구현체만 추가하면 된다.



---

## 7. 구현 우선순위 (v0.2.1)

| 우선순위 | 작업 | 선행 조건 | 영향 |
|---------|------|---------|------|
| P0 | `dag_edges` 테이블 DDL + `insert_dag_edge()` helper 추가 | 없음 | spec 08 sec 9, spec 09 공통 기반 |
| P1 | IngestOrchestrator에서 edges 즉시 기록 | P0 | Canvas, sync 가속 |
| P1 | `dashboard.md` 자동 작성 (IngestWorker) | P0 | 사용자 진행률 확인 |
| P2 | Plugin status bar polling | P1 | plugin UX |
| P2 | Canvas 자동 생성 (`_write_build_canvas`) | P1 | 지식 구조 시각화 |
| P3 | `curator_query()` trace 필드 추가 | 없음 | 에이전트 투명성 |
| P3 | Plugin "Sources & Trace" 패널 | P3 above | Ask Gemini UX |
| P4 | `DashboardSyncCallbacks` + `wiki sync` 연동 | P1 | sync 진행률 표시 |

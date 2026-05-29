# 05. Sync Backprop 및 증분 빌드

본 명세서는 지식 DAG를 딥러닝 신경망처럼 취급하여 오류 발생 시 역추적(Backpropagate)하고
특정 노드만 증분 수리(Incremental Rebuild)하는 동기화 로직을 정의한다.

---

## 1. 구버전 플랜의 두 가지 누락

**누락 1 — 단방향만 정의됨:**

구버전은 `L4 수정 → L3/L2 downgrade → 재빌드` (역방향)만 다뤘다.
실제로 가장 흔한 HITL 시나리오는 **L2 Atom 직접 수정**이며, 이 경우 순방향 전파 필요.

```
L4 수정 → 역방향 진단 → 문제 L2/L3 격리 → 순방향 재빌드
L2 수정 → 순방향 전파 → 의존 L3/L4 재빌드
L3 수정 → 순방향 전파 → 의존 L4 재빌드
```

**누락 2 — 사람이 검증한 노드를 덮어씀:**

재빌드가 사람이 직접 수정한 L4를 덮어쓰면 HITL의 의미가 없어진다.
스키마의 `is_verified_by_human` 필드를 반드시 활용해야 한다.

---

## 2. 오차 신호(Loss Signal) 감지

### 2.1. 파일 해시 변경 감지

```python
def detect_human_edits(vault_path: str, db_path: str) -> list[str]:
    """sync.py의 scan_for_changes()를 활용, 사람이 수정한 노드 식별"""
    report = scan_for_changes(vault_path, db_path)
    # modified에 포함된 노드 중 import_origin='human'이거나
    # 파일이 .curator/Collections/ 내부에 있는 것
    return [p for p in report.modified if is_curator_node(p)]
```

### 2.2. Loss Signal 유형

| 유형 | 설명 | 트리거 |
|------|------|--------|
| `hash_changed` | 노드 파일 내용 변경 감지 | `wiki sync` |
| `structural_gap` | Provenance 링크가 끊어짐 | `wiki lint` |
| `logical_gap` | 상위/하위 노드 주장 충돌 | LLM 검증 |
| `user_flagged` | `is_flagged_for_agent: true` 설정 | 사용자 직접 |

---

## 3. 양방향 역전파 알고리즘

### 3.1. 역방향 패스 (L4/L3 수정 시)

```python
def backward_pass(modified_node_id: str) -> AffectedSubgraph:
    """
    수정된 상위 노드에서 출발, Provenance를 타고 하위 노드로 역추적
    원인이 된 L2/L3를 찾아 재빌드 대상 격리
    """
    layer = _layer_for_id(modified_node_id)
    affected = set()

    if layer == "exhibition":
        fm = _read_fm(modified_node_id)
        for con_id in fm.get("core_concepts", []):
            affected.add(con_id)
            # L3에서 L2로 한 단계 더 역추적
            con_fm = _read_fm(con_id)
            for atm_id in con_fm.get("atom_ids", []):
                affected.add(atm_id)

    elif layer == "concept":
        fm = _read_fm(modified_node_id)
        for atm_id in fm.get("atom_ids", []):
            affected.add(atm_id)

    return AffectedSubgraph(root=modified_node_id, nodes=affected)
```

### 3.2. 순방향 패스 (L2/L3 수정 시)

```python
def forward_pass(modified_node_id: str) -> AffectedSubgraph:
    """
    수정된 하위 노드에서 출발, 이 노드를 참조하는 상위 노드를 모두 찾아 재빌드 대상으로 표시
    """
    layer = _layer_for_id(modified_node_id)
    affected = set()

    if layer == "atom":
        # 이 ATM을 포함하는 모든 CON 찾기
        dependent_cons = db.find_concepts_containing_atom(modified_node_id)
        for con_id in dependent_cons:
            affected.add(con_id)
            # CON을 포함하는 EXH도 영향받음
            dependent_exhs = db.find_exhibitions_containing_concept(con_id)
            affected.update(dependent_exhs)

    elif layer == "concept":
        dependent_exhs = db.find_exhibitions_containing_concept(modified_node_id)
        affected.update(dependent_exhs)

    return AffectedSubgraph(root=modified_node_id, nodes=affected)
```

---

## 4. 증분 재빌드 (Incremental Rebuild)

### 4.1. `is_verified_by_human` 보호

```python
def incremental_rebuild(subgraph: AffectedSubgraph):
    """영향받은 서브그래프 내에서 검증된 노드를 보호하며 재빌드"""
    for node_id in subgraph.nodes:
        fm = _read_fm(node_id)

        if fm.get("is_verified_by_human"):
            # 보호: 이 노드 자체는 건드리지 않음
            # 단, 이 노드가 수정 트리거라면 상위 노드는 재빌드
            if node_id == subgraph.root:
                forward_pass(node_id)  # 상위 노드 재빌드
            continue

        # 재빌드 대상을 ingest_jobs에 backprop 트리거로 큐잉
        db.enqueue_job(
            source_id=get_source_for_node(node_id),
            job_type=f"rebuild_{_layer_for_id(node_id)}",
            trigger="backprop"
        )
```

### 4.2. 재빌드 비율

전체 1,000개 노드 중 오류 서브그래프 8개 노드만 재빌드:

- 토큰 비용 99% 절감
- 무관한 노드 변경 없음
- `ingest_jobs.trigger='backprop'`으로 일반 ingest와 구분

---

## 5. `wiki sync` 명령 진입점

```python
def wiki_sync(backward: bool = False, target_id: str = "", full: bool = False):
    """
    기본값 (인수 없음): run_incremental_sync() — hash 기반 변경 감지 후 최소 재검증
                       변경 없으면 ~1초, 변경 있으면 변경 범위만 Mode C 검증
                       (spec 08 섹션 9.2에서 도입)

    --full           : run_mode_a() — 전체 DAG 재검증 (드물게 필요)
    --backward       : backprop 역방향 진단 후 증분 재빌드
    --target <id>    : 특정 노드 지정 (--backward와 함께 사용)
    """
    if backward:
        nodes = [target_id] if target_id else detect_human_edits(vault_path, db_path)
        for node_id in nodes:
            layer = _layer_for_id(node_id)
            subgraph = (backward_pass(node_id)
                        if layer in ("exhibition", "concept")
                        else forward_pass(node_id))
            incremental_rebuild(subgraph)
            # backprop으로 CON이 변경된 경우 EXH 캐시 무효화 (spec 07 섹션 4.4)
            if layer == "concept" or (layer == "atom" and subgraph.nodes):
                for nid in subgraph.nodes:
                    if _layer_for_id(nid) == "concept":
                        invalidate_exh_cache_for_concept(nid, db_path)
    elif full:
        run_mode_a()   # 전체 스캔 (명시적 요청 시에만)
    else:
        run_incremental_sync(paths, client, config)  # 기본값
```

**기본 동작이 `run_mode_a()` → `run_incremental_sync()`로 바뀐 이유**:
변경이 없는 일반적인 `wiki sync` 실행에서 10분짜리 전체 재검증을 없애기 위함.
hash 스캔만으로 0.6초 내 완료, 변경이 있을 때만 Mode C LLM 검증 실행.

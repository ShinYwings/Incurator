# 07. Exhibition 생성 모델 — Query-time 동적 합성

**핵심 질문**: 에이전트가 MCP로 지식을 가져올 때 Exhibition은 어떻게 생성되어야 하는가?

---

## 1. 문제: 정적 Pre-baked Exhibition의 한계

현재 `wiki curate` 명령은 `curate.yml`(Knowledge Requirement Spec)을 기반으로 EXH를
사전 생성한다. 이 방식의 문제:

- `curate.yml`이 정의하지 않은 주제는 EXH가 없어서 에이전트가 빈손으로 응답
- 에이전트 대화 흐름에서 발생하는 즉흥적 질문에 대응 불가
- 동일 L3 Concept을 다른 관점에서 합성한 EXH가 필요해도 재생성 방법 없음

**결론**: MCP로 지식을 조회할 때 해당 쿼리에 맞는 Exhibition을 **즉석에서 생성**해야 한다.

---

## 2. Exhibition 3-Tier Lifecycle

```
Tier 1: Pre-baked    wiki curate + curate.yml  워크스페이스 정의 항목, 장기 보존
         ↓ 에이전트가 더 좋은 합성 결과 발견
Tier 2: Query-gen    curator_query(question)   쿼리 시 즉석 생성, 워크스페이스 캐시
         ↓ 사용자가 "이거 남겨줘" 승인
Tier 3: Promoted     02_Wiki/로 이동            사람 검증, 영구 보존, is_verified_by_human=true
```

**핵심 원칙**: Exhibition은 **워크스페이스 단위**로 캐시되고 여러 채팅 세션이 공유한다.
Chat session은 Exhibition의 소유자가 아니라 Exhibition을 생성하는 트리거다.

---

## 3. 신규 EXH frontmatter 필드

```yaml
---
id: EXH-abcdef01
type: exhibition
core_concepts:
  - "03_Concepts/CON-12345678"
  - "03_Concepts/CON-9abcdef0"
confidence_score: 0.91
generation_trigger: query          # wiki_curate | query | manual | backprop
generation_query: "What is self-attention mechanism?"
workspace_id: "transformer_paper"  # 어느 워크스페이스에서 생성됐는지
is_verified_by_human: false
promoted_to_wiki: false            # true면 02_Wiki/에 복사본 존재
last_updated: "2026-05-28T10:00:00Z"
---
```

---

## 4. `curator_query` MCP 도구 개선

### 4.1. 현재 동작

```
curator_query(question) → L3 검색 → LLM 즉석 합성 → 텍스트 반환
```

합성 결과가 저장되지 않아 동일 질문에도 매번 LLM 재호출.

### 4.2. v0.2.1 동작 — Exhibition Cache + On-demand 생성

```python
def curator_query(
    question: str,
    workspace_id: str,
    force_new: bool = False,
) -> dict:
    """
    1. 관련 L3 Concept 검색
    2. 기존 EXH 캐시 확인 (같은 워크스페이스 + 같은 Concept 조합)
    3. 캐시 히트 → 기존 EXH 반환
    4. 캐시 미스 → 새 EXH 생성 + 저장 + 반환
    """
    # Step 1: 쿼리와 관련된 L3 Concept 검색
    relevant_concepts = search_concepts(question, top_k=5)
    concept_ids = [c.id for c in relevant_concepts]

    if not force_new:
        # Step 2: 기존 EXH 중 동일 concept 조합 확인
        cached = find_cached_exhibition(concept_ids, workspace_id)
        if cached:
            return {"exhibition": cached, "cache_hit": True}

    # Step 3: 새 EXH 생성 (L1 접근 금지, L2+L3만 사용)
    exh = generate_exhibition_from_concepts(
        concept_ids=concept_ids,
        generation_query=question,
        workspace_id=workspace_id,
    )

    # Step 4: .curator/Collections/04_Exhibitions/에 저장
    save_exhibition(exh)

    return {"exhibition": exh, "cache_hit": False}
```

### 4.3. 캐시 히트 판단 기준

전체 일치 방식으로 구현 (v0.2.1 단순화):

```python
def find_cached_exhibition(concept_ids: list[str], workspace_id: str) -> EXH | None:
    """
    동일 concept_ids 집합 + 동일 workspace_id 인 EXH가 존재하면 반환.
    is_cache_invalidated=True 인 EXH는 캐시 히트 대상에서 제외.
    의미론적 유사도 매칭은 v0.2.2에서 도입 예정.
    """
    key = frozenset(concept_ids)
    existing = db.find_exhibitions_by_concepts(concept_ids, workspace_id)
    for exh in existing:
        if frozenset(exh.core_concepts) == key and not exh.is_cache_invalidated:
            return exh
    return None
```

### 4.4. 캐시 무효화 (spec 05 backprop 연동)

spec 05의 backprop이 CON 노드를 수정하거나 재빌드 큐에 넣으면,
해당 CON을 참조하는 EXH의 캐시를 무효화한다.
`is_verified_by_human=True` EXH는 보호되어 무효화되지 않는다.

```python
def invalidate_exh_cache_for_concept(concept_id: str, db_path: str) -> list[str]:
    """
    concept_id를 core_concepts에 포함하는 모든 EXH의 캐시를 무효화.
    backprop._enqueue_next_phase() 또는 forward_pass() 완료 후 호출.
    반환값: 무효화된 EXH id 목록 (재빌드 큐잉 여부 결정용)
    """
    exh_ids = db.find_exhibitions_containing_concept(db_path, concept_id)
    invalidated = []
    for exh_id in exh_ids:
        fm = page_writer.read_frontmatter(get_exhibition_path(exh_id))
        if fm and fm.get("is_verified_by_human"):
            continue  # 사람이 검증한 EXH는 보호
        db.set_exh_cache_invalidated(db_path, exh_id, True)
        invalidated.append(exh_id)
    return invalidated
```

`ingest_jobs` 테이블의 `l4_exhibitions` 잡으로 재빌드 큐잉:

```python
for exh_id in invalidated_exh_ids:
    db.enqueue_job(
        db_path, source_id=None, job_type="l4_exhibitions",
        trigger="backprop", node_id=exh_id
    )
```

EXH frontmatter에 `is_cache_invalidated` 필드 추가:

```yaml
---
id: EXH-abcdef01
type: exhibition
is_verified_by_human: false
is_cache_invalidated: false   # backprop으로 CON이 변경되면 true
promoted_to_wiki: false
---
```

---

## 5. 채팅 세션과 Exhibition의 관계

세션은 Exhibition의 소유자가 아니다. Exhibition은 워크스페이스 수준의 지식 자산이다.

```
Workspace: transformer_paper
  ├── EXH-abc  "self-attention 메커니즘"  (세션 A에서 최초 생성)
  ├── EXH-def  "LSTM과의 비교"            (세션 A에서 최초 생성)
  └── EXH-ghi  "NLP 응용 사례"           (세션 B에서 최초 생성)

Chat Session A (workspace: transformer_paper)
  ├── Q1: "self-attention이 뭐야?" → EXH-abc 신규 생성
  ├── Q2: "LSTM이랑 비교해줘"     → EXH-def 신규 생성
  └── Q3: "self-attention 다시"   → EXH-abc 캐시 히트 (LLM 재호출 없음)

Chat Session B (workspace: transformer_paper)
  ├── Q1: "self-attention이 뭐야?" → EXH-abc 캐시 히트 (세션 A 것 재사용)
  └── Q2: "NLP 응용 사례"          → EXH-ghi 신규 생성
```

---

## 6. Exhibition 승격 (Promotion) 플로우

에이전트가 생성한 EXH 중 사용자가 가치 있다고 판단한 것을 `02_Wiki/`로 승격:

```python
# MCP 도구
def promote_exhibition(exh_id: str) -> dict:
    """Query-gen EXH를 02_Wiki/로 복사, is_verified_by_human=true 설정"""
    exh_path = get_exhibition_path(exh_id)
    wiki_path = f"02_Wiki/{derive_title(exh_id)}.md"

    # 02_Wiki/로 복사
    vault.copy(exh_path, wiki_path)

    # 원본 EXH 메타데이터 업데이트
    update_frontmatter(exh_id, {
        "is_verified_by_human": True,
        "promoted_to_wiki": True,
    })

    return {"promoted_to": wiki_path}
```

승격된 EXH는 `backprop` 재빌드 대상에서 제외된다 (`is_verified_by_human=true`).

---

## 7. `wiki curate`와의 관계

`wiki curate`는 `curate.yml`의 Knowledge Requirement Spec을 읽어 **Tier 1 Pre-baked EXH**를
생성하는 배치 작업이다. 내부적으로 동일한 `generate_exhibition_from_concepts()` 함수를
사용하며, `generation_trigger='wiki_curate'`로 구분된다.

```
wiki curate 실행 시:
  → curate.yml의 required_topics 읽기
  → 각 토픽에 맞는 L3 Concept 검색
  → Exhibition 생성 (curator_query와 동일 로직)
  → generation_trigger='wiki_curate' 로 저장
```

두 경로(배치/실시간)가 동일한 생성 함수를 공유하므로 품질 일관성 보장.

# 08. 성능 개선 및 서브에이전트 오케스트레이션 아키텍처

본 명세서는 현재 Incurator ingest 파이프라인이 왜 느린지 근본 원인을 전수조사하고,
현대 RAG/지식 그래프 시스템이 이 문제를 어떻게 해결했는지 기법을 분석하여,
Incurator가 채택할 수 있는 구체적 아키텍처를 설계한다.

**provider 가정**: Ollama(로컬), Gemini CLI(`agy`), Claude CLI(`claude`) 모두 지원.
direct API SDK 클라이언트는 llm.py에서 의도적으로 제거된 legacy 구현이므로 복구하지 않는다.

---

## 1. 현재 ingest가 왜 느린가 — 근본 원인 전수조사

### 1.1. 수치로 보는 병목 (50페이지 학술 논문 기준)

```
wiki add paper.pdf → run_l1_to_l3() (현재 v0.2.0):

[L1] pdfminer 파싱                              ~3-5초  (동기)
[L2] Pass 1 — Atom 추출:
     - Orchestrator 계획 LLM 1회               ~10-15초
     - Atom 20개, max_workers=3:
       7 배치 × 30초/배치 = 약 7분
[L3] Pass 2 — Concept 클러스터링:
     - 클러스터링 계획 LLM 1회                  ~15초
     - Concept 5개 순차 작성 × 45초/개 = 약 4분

총 소요: 약 11-12분 (전체 CLI 블로킹)
```

`wiki curate` (L4):
```
- 합성 계획 LLM 1회                             ~15초
- Exhibition 2개 순차 작성 × 60초/개 = 약 2분

총 소요: 약 2.5분 (별도 명령 블로킹)
```

### 1.2. 병목 원인 1 (최대 임팩트): "1 Atom = 1 LLM 호출" 구조

| 레이어 | 현재 LLM 호출 수 | 병렬화 | 실제 문제 |
|--------|----------------|--------|----------|
| L2 Atom | 1(계획) + N(원자당 1회) | max_workers=3 | N=20이면 7 배치, 약 7분 |
| L3 Concept | 1(계획) + M(컨셉당 1회) | 없음 — 완전 순차 | M=5이면 약 4분 |
| L4 Exhibition | 1(계획) + K(전시당 1회) | 없음 — 완전 순차 | K=2이면 약 2분 |

L2에 `ThreadPoolExecutor(max_workers=3)`은 이미 구현되어 있다.
**L3와 L4는 완전히 순차적이다.** 이것이 가장 빠른 개선 기회.

### 1.3. 병목 원인 2: thread-safety 버그 (현재 코드)

```python
# ingest_llm.py _run_parallel_workers() — 버그
executor.submit(_extract_atoms_for_task, task, paths, client, ...)
#                                                    ↑
#                     여러 스레드가 동일 client 인스턴스 공유
```

`OllamaClient`의 `httpx.Client`는 스레드 안전하지 않다.
Gemini/Claude CLI 클라이언트는 subprocess를 새로 spawn하므로 우연히 safe하지만,
공유 client 패턴 자체가 잘못되어 있어 수정이 필요하다.

### 1.4. 병목 원인 3: 전체 문서를 단일 excerpt로 전달

```python
excerpt = _build_excerpt(parsed.text, max_chars=30000)
# 이 30K 덩어리가 20개 Atom 호출 각각의 컨텍스트로 반복 전달
```

섹션 A의 Atom을 추출할 때 섹션 F, G, H의 내용이 컨텍스트에 섞임
→ 환각 유발 + 불필요한 토큰 낭비.

---

## 2. 현대 시스템의 해결 기법 (provider-agnostic)

### 2.1. Section-Aware Batch Extraction (가장 큰 임팩트)

**"N번 LLM 호출" → "1-3회 LLM 호출" + 섹션 컨텍스트 보존**

LlamaIndex, LangChain, GraphRAG 모두 이 패턴을 쓴다.
핵심: LLM에게 "이 Atom 하나를 위한 페이지를 써라" 대신
"이 문서의 모든 Atom을 JSON 배열로 추출하라"고 요청.

CTX 파일에는 이미 `<!-- section:id page:N -->` 마커가 포함되어 있다 (spec 02).
이 마커를 그대로 LLM에 전달하면 **배치 추출이면서도 섹션 귀속이 정확**하다.
spec 03의 ToC 청킹은 "섹션당 LLM 호출"이 아니라
**"50K chars를 초과하는 대형 문서를 그룹으로 묶는 도구"** 로 역할이 바뀐다.

```python
MAX_BATCH_CHARS = 50_000  # 모든 지원 provider의 context window에 안전하게 맞음

def run_l2_batch_extraction(
    paths: WikiPaths,
    client,           # OllamaClient | AntigravityCliClient | ClaudeCodeClient
    ctx_path: Path,   # CTX 파일 경로 — <!-- section:id page:N --> 마커 포함
    context_id: str,
    relpath: str,
    today: str,
    staging: Path,
) -> list[tuple[Path, Path, PageChange]]:
    """CTX 파일을 LLM에 전달, 모든 Atom을 배치 추출.

    CTX 파일에 section 마커가 있으므로 LLM이 source_section을 스스로 판단.
    문서가 MAX_BATCH_CHARS 이하: 1회 호출.
    초과 시: section 마커 기준으로 그룹 분할 → 그룹당 1회 (최대 2-3회).
    절대 atom당 1 LLM call 방식으로 퇴행하지 않음.
    """
    ctx_content = ctx_path.read_text(encoding="utf-8")
    body = _ctx_body_only(ctx_content)  # frontmatter 제거, section 마커 포함 body만

    chunks = _split_into_batches(body, MAX_BATCH_CHARS)

    staged = []
    for chunk in chunks:
        staged.extend(
            _extract_atoms_from_chunk(chunk, client, paths, context_id, relpath, today, staging)
        )
    return staged


def _split_into_batches(body: str, max_chars: int) -> list[str]:
    """
    <!-- section:id ... --> 마커를 경계로 본문을 분할.
    각 청크가 max_chars 이하가 되도록 섹션들을 묶음.
    마커가 없거나 단일 청크로 충분하면 리스트 1개 반환.
    """
    import re
    if len(body) <= max_chars:
        return [body]

    # <!-- section:... --> 마커를 경계로 분리
    parts = re.split(r'(?=<!-- section:)', body)
    batches, current, current_len = [], [], 0
    for part in parts:
        if current_len + len(part) > max_chars and current:
            batches.append("".join(current))
            current, current_len = [part], len(part)
        else:
            current.append(part)
            current_len += len(part)
    if current:
        batches.append("".join(current))
    return batches


def _extract_atoms_from_chunk(
    chunk: str, client, paths, context_id, relpath, today, staging
) -> list[tuple[Path, Path, PageChange]]:
    messages = [ChatMessage(role="user", content=f"""다음 문서에서 원자적 지식 단위(Atom)를 모두 추출하라.
각 Atom은 단 하나의 독립적인 사실/주장/방정식/기법이어야 한다.

문서에 <!-- section:id page:N --> 마커가 있다.
각 atom의 source_section_id에는 해당 atom과 가장 가까운 section id를 기록하라.

**반드시 JSON 배열만 반환하고 다른 텍스트를 포함하지 말 것.**

형식:
[
  {{
    "name": "항목 이름",
    "claim_type": "fact | claim | entity | procedure | relationship 중 하나",
    "one_liner": "한 문장 요약",
    "source_section_id": "가장 가까운 section id (없으면 빈 문자열)",
    "source_section_title": "해당 섹션 제목",
    "source_page": 페이지_번호_정수,
    "confidence": 0.0~1.0
  }},
  ...
]

문서:
{chunk}
""")]

    raw = client.chat(messages, json_mode=True, temperature=0.1)
    atoms_data = _parse_batch_atoms_json(raw)

    staged = []
    for atom_data in atoms_data:
        atom_id = _gen_id("ATM")
        content = _build_atom_page_from_data(atom_id, atom_data, context_id, relpath, today)
        final_path = paths.atoms / f"{atom_id}.md"
        staged_path = staging / f"02_Atoms__{atom_id}.md"
        staged_path.write_text(content, encoding="utf-8")
        change = PageChange(id=atom_id, path=f"02_Atoms/{atom_id}.md",
                            layer="02_Atoms", operation="created")
        staged.append((staged_path, final_path, change))
    return staged
```

`_parse_batch_atoms_json(raw)` — 기존 `_extract_json()` + `_parse_json_model()` 조합:

```python
def _parse_batch_atoms_json(raw: str) -> list[dict]:
    """
    provider가 반환하는 raw 텍스트에서 JSON 배열 추출.
    - OllamaClient: 순수 JSON 반환 (json_mode=True)
    - CLI providers: 마크다운 코드블록으로 감싸는 경우 있음 → _extract_json()으로 제거
    - 파싱 실패 시 빈 리스트 반환 (작업 실패 대신 graceful degradation)
    """
    text = _extract_json(raw)  # ```json ... ``` 제거
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []
```

Atom 페이지(.md) 작성은 **LLM 없이 Python 템플릿으로** 즉시 생성:

```python
def _build_atom_page_from_data(atom_id, data, context_id, relpath, today) -> str:
    """structured data → Atom 마크다운. LLM 호출 없음."""
    import hashlib, yaml

    body_text = f"# {data['name']}\n\n## Definition / Claim\n\n{data['one_liner']}\n"
    content_hash = hashlib.sha256(body_text.encode()).hexdigest()[:16]

    fm = {
        "id": atom_id,
        "type": "atom",
        "parent_source": f"01_Contexts/{context_id}",
        "source_path": f"[[{relpath.removesuffix('.md')}]]",
        "claim_type": data.get("claim_type", "fact"),
        "source_section_id": data.get("source_section_id", ""),
        "source_section_title": data.get("source_section_title", ""),
        "source_page": data.get("source_page", 0),
        "confidence_score": min(1.0, max(0.0, float(data.get("confidence", 0.8)))),
        "content_hash": content_hash,   # spec 08 섹션 9 incremental sync용
        "is_verified_by_human": False,
        "is_flagged_for_agent": False,
        "last_updated": today,
    }
    fm_str = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False)
    body = f"""# {data['name']}

## Definition / Claim

{data['one_liner']}

## Context

## Constraints

## Relations

[[01_Contexts/{context_id}]]
"""
    return f"---\n{fm_str}---\n\n{body.strip()}\n"
```

**비교:**

| | 현재 | Section-Aware Batch |
|--|------|---------------------|
| LLM 호출 수 (N=20 atoms, 50p) | 21회 | **1회** (50K 이하) / **2-3회** (초과) |
| 소요 시간 | ~7분 | **~15-45초** |
| 섹션 귀속 정확도 | 중간 (section당 1 call이었으므로 정확) | **동일** (section 마커 포함 전달) |
| provider 제약 | 없음 | 없음 (모든 provider) |
| 파싱 실패 | 빈번 (마크다운 구조 파싱) | 낮음 (JSON이 더 단순) |

### 2.2. Embedding-based L3 Clustering

**"LLM으로 클러스터 결정" → "수학으로 클러스터 결정"**

LightRAG, GraphRAG이 공통적으로 채택한 패턴.

```python
def cluster_atoms_by_embedding(
    paths: WikiPaths,
    atom_ids: list[str],
    client,
    eps: float = 0.35,
) -> list[list[str]]:
    """임베딩 기반 Atom 클러스터링. LLM 클러스터링 계획 호출 1회 제거.

    Provider별 전략:
    - OllamaClient: /api/embeddings 엔드포인트 사용 (로컬, 빠름)
    - CLI clients: sentence-transformers 폴백 (로컬, LLM 불필요)
    - 둘 다 불가: 기존 LLM 클러스터링 폴백
    """
    import numpy as np
    from sklearn.cluster import DBSCAN

    summaries = []
    valid_ids = []
    for aid in atom_ids:
        s = _atom_summary(paths, aid)
        if s:
            summaries.append(s["one_liner"] or s["name"])
            valid_ids.append(aid)

    if len(valid_ids) < 2:
        return [valid_ids] if valid_ids else []

    embeddings = _get_embeddings(summaries, client)
    if embeddings is None:
        return None  # caller가 LLM 클러스터링으로 폴백

    labels = DBSCAN(eps=eps, min_samples=2, metric="cosine").fit_predict(
        np.array(embeddings)
    )

    clusters: dict[int, list[str]] = {}
    for i, label in enumerate(labels):
        effective_label = label if label != -1 else max(clusters.keys(), default=-1) + 1
        clusters.setdefault(effective_label, []).append(valid_ids[i])
    return list(clusters.values())


def _get_embeddings(texts: list[str], client) -> list[list[float]] | None:
    """Provider별 임베딩 전략."""
    # Ollama: 로컬 임베딩 모델 (nomic-embed-text 등)
    if isinstance(client, OllamaClient) or (
        isinstance(client, FailoverClient)
        and isinstance(client.active_provider, OllamaClient)
    ):
        return _embed_via_ollama(texts, client)

    # 폴백: sentence-transformers (로컬, CPU, provider 독립)
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model.encode(texts, convert_to_numpy=False).tolist()
    except ImportError:
        return None  # 의존성 없으면 LLM 클러스터링으로 폴백


def _embed_via_ollama(texts: list[str], client: OllamaClient) -> list[list[float]] | None:
    """Ollama /api/embeddings 엔드포인트."""
    import httpx
    # nomic-embed-text 또는 mxbai-embed-large 등 전용 임베딩 모델
    embed_model = "nomic-embed-text"
    results = []
    try:
        with httpx.Client(timeout=30.0) as http:
            for text in texts:
                r = http.post(
                    f"{client.host}/api/embeddings",
                    json={"model": embed_model, "prompt": text},
                )
                r.raise_for_status()
                results.append(r.json()["embedding"])
        return results
    except Exception:
        return None
```

**Embedding 클러스터링 불가 시 폴백**: 기존 LLM 클러스터링 계획 호출 1회.
이 경우에도 L2 batch extraction 덕분에 전체 시간은 크게 단축된다.

### 2.3. Two-Tier Model Strategy

```
L2 Atom extraction (추출, 정형화)
  → 어떤 provider든: Flash/Fast 모델 (Gemini Flash, Haiku 등)
  → 창의성 불필요, 빠른 정보 추출이 목표

L3 Concept clustering
  → embedding + DBSCAN (LLM 불필요)
  → Concept 페이지 작성: Flash 모델 (짧은 컨텍스트, 병렬 가능)

L4 Exhibition synthesis (wiki curate)
  → Pro/Think 모델 (Gemini Pro, Sonnet 등)
  → 여러 Concept의 관계를 깊이 이해하는 통찰력 있는 합성 필요
```

Incurator는 이미 `llm_cfg["gemini_flash_model"]` / `"gemini_think_model"` 을 구분하고 있다.
L2/L3에는 flash, L4에는 think 모델을 쓰도록 `IngestOrchestrator`에서 선택:

```python
def _make_flash_client(self) -> object:
    """L2/L3용 빠른 모델 클라이언트."""
    # config에서 flash 모델 선택
    flash_cfg = dict(self.config)
    llm = dict(flash_cfg.get("llm", {}))
    # antigravity-cli면 flash_model로 override
    if llm.get("primary") == "antigravity-cli":
        llm["antigravity_flash_model"] = llm.get(
            "antigravity_flash_model", DEFAULT_ANTIGRAVITY_FLASH_MODEL
        )
    flash_cfg["llm"] = llm
    return build_client(flash_cfg)

def _make_think_client(self) -> object:
    """L4용 품질 모델 클라이언트 (wiki curate에서 사용)."""
    think_cfg = dict(self.config)
    llm = dict(think_cfg.get("llm", {}))
    if llm.get("primary") == "antigravity-cli":
        llm["antigravity_flash_model"] = llm.get(
            "antigravity_think_model", DEFAULT_ANTIGRAVITY_THINK_MODEL
        )
    think_cfg["llm"] = llm
    return build_client(think_cfg)
```

---

## 3. 개선 후 성능 예측

```
wiki add paper.pdf → run_l1_to_l3() (v0.2.1 목표, 백그라운드):

[L1] PyMuPDF 파싱                      ~2-3초
[L2] Batch extraction:
     - 전체 문서 → 1회 LLM 호출         ~20-30초
     - Atom 페이지 작성 (템플릿)         ~1초
[L3] Embedding 클러스터링:
     - Ollama embedding / sentence-transformers  ~3-5초
     - DBSCAN                           ~0.1초
     - Concept 5개 병렬 작성 (3 workers)  ~30-45초
총 L1-L3: 약 55-85초 ≈ 1-1.5분

wiki curate (v0.2.1 목표):
     - 합성 계획 1회                    ~15초
     - Exhibition 2개 병렬 작성          ~30-60초
총 L4: 약 45-75초

현재 대비:
  wiki add:    11-12분 → 1-1.5분  (약 8-10배 단축)
  wiki curate: 2.5분  → 45-75초  (약 2-3배 단축)
```

---

## 4. 서브에이전트 오케스트레이션 설계

### 4.1. "서브에이전트"의 정확한 정의

```
"서브에이전트" = 독립 LLM 클라이언트 인스턴스 + ThreadPoolExecutor worker
"대장 에이전트" = IngestOrchestrator (작업 분배 + 상태 조율)

구현: Python ThreadPoolExecutor, in-process.
외부 프로세스/MCP 에이전트 방식이 아님 (IPC 오버헤드 > LLM 절약 효과).
```

### 4.2. IngestOrchestrator 구조

```python
# backend/src/curator/ingest_orchestrator.py (신규)

from concurrent.futures import ThreadPoolExecutor, as_completed

class IngestOrchestrator:
    """L2-L3 파이프라인 오케스트레이터. wiki add 범위만 담당 (L4 제외)."""

    def __init__(self, paths: WikiPaths, config: dict):
        self.paths = paths
        self.config = config

    def run_l2_batch(self, source_id: int, staging: Path, today: str) -> list:
        """L2 서브에이전트: single-pass batch extraction. 1 LLM 호출."""
        client = self._make_flash_client()
        return run_l2_batch_extraction(
            self.paths, client, document_text, context_id, relpath, today, staging
        )

    def run_l3_parallel(
        self, concept_plans: list, staging: Path, today: str, artist_persona=None
    ) -> list:
        """L3 서브에이전트: Concept 페이지 병렬 작성.

        현재 코드는 완전 순차(_run_pass2_concepts의 내부 루프).
        클러스터링 계획(1 LLM 호출)은 순차 유지, 페이지 작성만 병렬화.
        """
        max_workers = min(3, len(concept_plans))
        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 각 worker마다 독립 client 인스턴스 — thread-safety 보장
            future_map = {
                executor.submit(
                    self._write_one_concept,
                    plan,
                    self._make_flash_client(),  # 독립 인스턴스
                    staging,
                    today,
                    artist_persona,
                ): plan
                for plan in concept_plans
            }
            for future in as_completed(future_map):
                result = future.result()
                if result:
                    results.append(result)
        return results

    def run_l4_parallel(
        self, synthesis_plans: list, staging: Path, today: str, artist_persona=None
    ) -> list:
        """L4 서브에이전트: Exhibition 페이지 병렬 작성.

        wiki curate에서만 호출됨. wiki add 체인에서는 호출되지 않음.
        """
        max_workers = min(2, len(synthesis_plans))
        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    self._write_one_exhibition,
                    plan,
                    self._make_think_client(),  # L4는 think 모델
                    staging,
                    today,
                    artist_persona,
                ): plan
                for plan in synthesis_plans
            }
            for future in as_completed(future_map):
                result = future.result()
                if result:
                    results.append(result)
        return results

    def _write_one_concept(self, plan, client, staging, today, artist_persona):
        """단일 ConceptPlan → Concept 페이지. Thread-safe."""
        # ingest_llm.py _run_pass2_concepts() 루프 body 분리
        pass

    def _write_one_exhibition(self, plan, client, staging, today, artist_persona):
        """단일 SynthesisPlan → Exhibition 페이지. Thread-safe."""
        # ingest_llm.py _run_pass3_synthesis() 루프 body 분리
        pass
```

### 4.3. IngestWorker와의 관계 (spec 04 연동)

```
IngestWorker (spec 04) — 잡 큐 처리자
  └─ _process_job(job)
        ├─ job_type="l2_atoms"    → IngestOrchestrator.run_l2_batch()
        └─ job_type="l3_concepts" → IngestOrchestrator.run_l3_parallel()

wiki curate (별도 CLI 커맨드)
        └─ IngestOrchestrator.run_l4_parallel()  ← IngestWorker 밖에서 호출
```

`ingest_jobs` 테이블의 `l4_exhibitions` job_type은
**normal wiki add 체인에서는 사용하지 않는다.**
spec 05(Sync Backprop)의 역전파 재빌드 시에만 사용된다:
```sql
-- 역전파 시 특정 EXH 재합성 요청
INSERT INTO ingest_jobs (job_type, trigger, ...) VALUES ('l4_exhibitions', 'backprop', ...);
```

---

## 5. thread-safety 수정

```python
# ingest_llm.py _run_parallel_workers() — 수정 전
future_to_task = {
    executor.submit(_extract_atoms_for_task, task, paths, client, ...): task
    #                                                        ↑ 공유 버그
}

# 수정 후 — 각 worker에 독립 클라이언트
from .llm import build_client

def _run_parallel_workers(tasks, paths, client_config, callbacks, ...):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(
                _extract_atoms_for_task,
                task, paths,
                build_client(client_config),  # 독립 인스턴스
                ...
            ): task
        }
```

`build_client(config)`를 각 submit 시점에 호출하여 독립 인스턴스 생성.
`OllamaClient(httpx.Client)`, `AntigravityCliClient`, `ClaudeCodeClient` 모두 this 방식으로 safe.

---

## 6. SQLite 동시성 안전성

병렬 worker 스레드는 staging 디렉토리에만 파일 작성 (파일명이 atom_id로 유일):

```python
staged_path = staging / f"02_Atoms__{atom_id}.md"  # 각 worker가 다른 파일명
staged_path.write_text(content)  # 충돌 없음
```

SQLite 쓰기는 Orchestrator가 모든 worker 완료 후 메인 스레드에서 일괄 커밋:

```python
# worker 완료 후 메인 스레드에서:
for staged_path, final_path, change in all_staged:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(staged_path, final_path)

with db.connect(paths.state_db) as conn:
    conn.execute("BEGIN")
    for change in all_changes:
        conn.execute("UPDATE sources SET ...", ...)
    conn.execute("COMMIT")
```

WAL 모드 + 단일 writer(Orchestrator 메인 스레드) → race condition 없음.

---

## 7. 구현 우선순위 (v0.2.1)

### P0 — thread-safety 수정 (버그 픽스, 즉시)

- `_run_parallel_workers()`에서 공유 client → `build_client(config)` 독립 인스턴스
- 기존 테스트 통과 확인

### P1 — 핵심 속도 개선

- **`run_l2_batch_extraction()`**: 20 LLM 호출 → 1 호출, 모든 provider 지원
- **`_build_atom_page_from_data()`**: 템플릿 기반 Atom 페이지 생성 (LLM 없음)
- **`_parse_batch_atoms_json()`**: 기존 `_extract_json()` + Pydantic 활용한 파싱

### P2 — L3/L4 병렬화

- **`IngestOrchestrator.run_l3_parallel()`**: Concept 페이지 병렬 작성 (max_workers=3)
- **`IngestOrchestrator.run_l4_parallel()`**: Exhibition 페이지 병렬 작성 (max_workers=2, wiki curate에서만)
- `ingest_llm.py` 내부 루프 body → `ingest_orchestrator.py`로 분리

### P3 — Embedding 클러스터링

- `cluster_atoms_by_embedding()`: Ollama embedding 우선, sentence-transformers 폴백
- LLM 클러스터링 계획 호출 제거 (폴백만 유지)
- `sklearn` 의존성 추가 (`pyproject.toml`)

### P4 — v0.2.1로 당김

- 섹션별 병렬 L2: CTX가 여러 section-aware batch로 쪼개지고 client clone이 가능하면
  `ThreadPoolExecutor(max_workers=3)`로 병렬 실행.
- Two-tier model 자동 선택 자동화: shared `models.json`의 `tier` 필드와
  `antigravity_flash_model` / `antigravity_think_model` 설정을 사용한다.
- Streaming L3 start는 global L3 coverage/status 전이와 충돌하므로 v0.2.2의
  pipeline-state redesign 항목으로만 남긴다.

---

## 8. 현재 retrieval 시스템과의 충돌 여부

**결론: 충돌하지 않는다.**

QMD(BM25+vector) 검색 엔진은 ingest 파이프라인과 독립된 모듈이다.
`search.py`의 `qmd` 바이너리는 ingest 중에 호출되지 않고,
ingest 완료 후 `wiki reindex`로 인덱스를 갱신한다.

ThreadPoolExecutor 병렬화도 동일:
- 각 worker는 staging에만 파일 작성 (서로 다른 파일명)
- SQLite는 Orchestrator 메인 스레드만 커밋
- QMD sqlite 인덱스와 curator state.sqlite는 별도 파일

**기술적 blocker 없음.**

---

## 9. wiki sync 성능 개선

`wiki add`(L1-L3)와 `wiki curate`(L4)는 LLM 호출 횟수가 병목이지만,
`wiki sync`는 구조가 다르다. LLM 호출보다 **변경 감지 로직 없음**이 핵심 병목이다.

### 9.1. 현재 wiki sync가 느린 이유 (근본 원인)

```
현재 wiki sync Mode A (200개 노드 기준):

[파일 I/O]  EXH 전체 → CON 전체 → ATM 전체 → CTX 전체 순회
             각 노드 = frontmatter 파일 1회 읽기
             200개 × ~5ms = ~1초 (그나마 빠른 편)

[이중 패스]  finalize_routing_tables():
             Collections/ 전체 재스캔 (이미 읽은 파일 다시 읽음)
             index.md / ledger.md / log.md 재빌드

[LLM 병목]  Mode C concept 검증:
             concept 50개 × 30초/call ÷ max_workers=4 = 약 6분
             ← orchestrated_pipeline Phase 3에서 ThreadPoolExecutor 이미 추가됨
             → 여전히 느린 이유: 변경 없는 concept도 매번 재검증

[연쇄 효과] 변경된 것이 ATM 1개뿐이어도,
             그 ATM이 속한 CON → 그 CON이 속한 EXH 전부 재검증
             영향 범위를 좁히는 로직 없음
```

**핵심 병목 요약**:

| 병목 | 원인 | 현재 영향 |
|------|------|----------|
| 전체 재검증 | 변경 감지 없음, 항상 전체 Mode A | 6-10분 |
| 이중 파일 스캔 | Mode A 후 routing table rebuild 재스캔 | ~2초 |
| DAG 구조 파일 기반 | SQL 없음, 모든 관계를 파일에서 추출 | ~1초 + 코드 복잡도 |

`wiki add`, `wiki curate`, `wiki sync` 세 명령을 연달아 쓰면 **20분 이상** 소요된다.

### 9.2. GraphRAG 방식: hash 기반 incremental sync

GraphRAG, LightRAG, LlamaIndex 모두 채택한 패턴:
**노드 content hash를 저장하고, 변경된 노드와 그 다운스트림만 재검증.**

```python
# ingest 시 모든 노드 파일에 content_hash frontmatter 기록
# (ingest_orchestrator.py, _build_atom_page_from_data() 등)

def _hash_file_content(path: Path) -> str:
    """frontmatter 제외 body만 해시. frontmatter 변경(last_updated 등)으로 오탐 방지."""
    text = path.read_text(encoding="utf-8")
    # frontmatter 블록 제거 후 body만 해시
    if text.startswith("---"):
        parts = text.split("---", 2)
        body = parts[2] if len(parts) >= 3 else text
    else:
        body = text
    return hashlib.sha256(body.encode()).hexdigest()[:16]
```

```python
# sync.py — 신규 함수

def run_incremental_sync(
    paths: WikiPaths,
    client,
    config: dict,
    callbacks: Optional[SyncCallbacks] = None,
) -> SyncRepairResult:
    """
    변경된 노드와 그 다운스트림만 재검증.
    변경 없으면 수 초 내 완료.

    알고리즘:
    1. 전 노드 body hash 계산 → frontmatter.content_hash와 비교
    2. 변경된 노드 집합(changed) 추출
    3. changed의 downstream 노드 집합 확장 (dag_edges SQL 사용)
    4. 확장된 집합에 대해 Mode C 검증 실행
    """
    changed_nodes = _find_changed_nodes(paths)
    if not changed_nodes:
        # routing table만 빠르게 갱신 후 종료 — 10분 → ~1초
        finalize_routing_tables(paths)
        return SyncRepairResult()

    # 변경된 노드와 영향받는 다운스트림만 검증
    affected = _expand_downstream_via_sql(paths, changed_nodes)
    return run_mode_b(paths, list(affected), client=client, callbacks=callbacks)


def _find_changed_nodes(paths: WikiPaths) -> list[str]:
    """body content hash가 frontmatter.content_hash와 다른 노드 ID 반환."""
    changed = []
    for layer_dir in (paths.contexts, paths.atoms, paths.concepts, paths.exhibitions):
        for md_path in sorted(layer_dir.glob("*.md")):
            fm = page_writer.read_frontmatter(md_path)
            if not fm:
                continue
            stored_hash = fm.get("content_hash", "")
            current_hash = _hash_file_content(md_path)
            if stored_hash != current_hash:
                changed.append(fm["id"])
    return changed


def _expand_downstream_via_sql(paths: WikiPaths, node_ids: list[str]) -> set[str]:
    """
    dag_edges 테이블로 변경된 노드의 다운스트림 전파.
    spec 09의 dag_edges 테이블 (state.sqlite)을 읽어 O(1) SQL 조회.
    """
    with db.connect(paths.state_db) as conn:
        affected = set(node_ids)
        queue = list(node_ids)
        while queue:
            batch = queue[:50]
            queue = queue[50:]
            placeholders = ",".join("?" * len(batch))
            rows = conn.execute(
                f"SELECT to_id FROM dag_edges WHERE from_id IN ({placeholders})",
                batch,
            ).fetchall()
            for row in rows:
                if row["to_id"] not in affected:
                    affected.add(row["to_id"])
                    queue.append(row["to_id"])
    return affected
```

### 9.3. SQLite dag_edges 테이블

`_expand_downstream_via_sql()`을 쓰려면 state.sqlite에 edges 테이블이 필요.
이 테이블은 **spec 09(Visualization)**에서도 Canvas 생성에 사용하므로 공유 인프라다.

```sql
-- db.py에 추가 (state.sqlite)
CREATE TABLE IF NOT EXISTS dag_edges (
    id          TEXT PRIMARY KEY,   -- '{from_id}->{to_id}'
    from_id     TEXT NOT NULL,      -- ATM-xxx, CON-xxx 등
    to_id       TEXT NOT NULL,      -- CON-xxx, EXH-xxx 등
    edge_type   TEXT NOT NULL,      -- 'extracted_from' | 'clustered_to' | 'synthesized_to'
    source_id   TEXT REFERENCES sources(id),
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dag_edges_from ON dag_edges(from_id);
CREATE INDEX IF NOT EXISTS idx_dag_edges_to   ON dag_edges(to_id);
```

IngestOrchestrator가 노드 생성 시 즉시 edges 기록:

```python
# ingest_orchestrator.py — run_l2_batch() 완료 후
for atom_id in created_atom_ids:
    db.insert_dag_edge(paths.state_db, from_id=context_id, to_id=atom_id,
                       edge_type="extracted_from", source_id=source_id)

# run_l3_parallel() 완료 후
for concept_id, atom_ids in concept_clusters.items():
    for atom_id in atom_ids:
        db.insert_dag_edge(paths.state_db, from_id=atom_id, to_id=concept_id,
                           edge_type="clustered_to", source_id=source_id)
```

### 9.4. finalize_routing_tables() 개선

현재 구현은 Collections/ 전체를 다시 스캔하여 index.md를 재빌드한다.
dag_edges + atoms/concepts 테이블이 있으면 SQL SELECT로 대체 가능:

```python
def finalize_routing_tables(paths: WikiPaths) -> None:
    """
    현재: Collections/ 전체 파일 스캔 → index.md 재빌드  (~2초)
    개선: SQL SELECT FROM dag_edges + sources → index.md 재빌드  (~50ms)
    """
    with db.connect(paths.state_db) as conn:
        # 전체 노드 ID + 레이어 매핑을 SQL로 조회
        ctx_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM sources WHERE id LIKE 'CTX-%'"
        ).fetchall()]
        # ... atoms, concepts, exhibitions도 동일
        # index.md 재빌드 (파일 스캔 없음)
```

**주의**: dag_edges 테이블이 없는 구버전 vault와의 호환을 위해
기존 파일 스캔 방식을 폴백으로 유지.

### 9.5. 개선 후 wiki sync 성능 예측

```
wiki sync (hash-based incremental, 200노드 기준):

[변경 없음]
  hash 스캔 (200개):   ~0.5초
  routing table 재빌드: ~0.1초  (SQL 기반)
  총:                  ~0.6초   (현재 6-10분 → 0.6초: 600배 단축)

[10% 노드 변경 (20개 변경)]
  hash 스캔:             ~0.5초
  downstream 확장 (SQL): ~0.1초
  Mode C 재검증 (20개):  ~2.5분  (20개 × 30초 ÷ max_workers=4)
  routing table 재빌드:  ~0.1초
  총:                    ~2.6분  (현재 6-10분 → 2.6분: 3-4배 단축)
```

가장 일반적인 시나리오("wiki sync로 DAG 무결성 확인" — 실제 변경 없음):
**10분 → 0.6초**.

### 9.6. wiki sync 구현 우선순위

| 우선순위 | 작업 | 선행 조건 |
|---------|------|---------|
| P0 | `content_hash` frontmatter 필드를 ingest 시 모든 신규 노드에 기록 | spec 08 P1 구현 시 함께 |
| P1 | `_find_changed_nodes()` + `run_incremental_sync()` 구현 | content_hash 필드 필요 |
| P1 | `dag_edges` 테이블 추가 (db.py) | spec 09와 공유 |
| P2 | `_expand_downstream_via_sql()` 구현 | dag_edges 필요 |
| P2 | `finalize_routing_tables()` SQL 기반 재작성 | dag_edges 필요 |

### 9.7. orchestrated_pipeline Phase 3와의 관계

`docs/plans/orchestrated_pipeline_and_persona_system.md` Phase 3에서
sync.py Mode C에 `ThreadPoolExecutor(max_workers=4)`가 이미 추가되어 있다.
이것은 "병렬 검증"이고, 본 섹션의 개선은 "검증 대상 축소"다. 두 최적화는 독립적이며 누적된다:

```
현재:   concept 50개 × 30초 ÷ max_workers=4 = 6분
hash 후: concept 5개 변경 × 30초 ÷ max_workers=4 = 37초
```

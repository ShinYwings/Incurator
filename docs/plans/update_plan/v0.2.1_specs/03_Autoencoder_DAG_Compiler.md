# 03. ToC 기반 지식 압축 및 DAG 컴파일 (HITL 오토인코더 아키텍처)

본 명세서는 100% 완전하게 수집된 구조적 L1을 바탕으로, 백엔드가 어떻게 지식을 압축하여
잠재 공간(Latent Space)을 형성하고 이를 다시 지식망으로 펼쳐내는지 서술한다.

---

## 1. 오토인코더 계층 매핑

```
[L1 Context — Raw Document]
        ↓  ENCODER (ToC-Guided Chunking → Atom 추출)
[L2 Atoms — Latent Space]  ← 사람이 직접 읽고 수정 가능한 명시적 잠재 공간
        ↓  DECODER (Concept 클러스터링)
[L3 Concepts — Semantic Cluster]
        ↓  DECODER (Exhibition 합성, L1 절대 금지)
[L4 Exhibitions — Final Output]
```

딥러닝 오토인코더와의 결정적 차이:
- 잠재 공간이 단일 벡터가 아닌 **수백 개의 독립 마크다운 파일(노드)** 집합
- 사람(HITL)이 잠재 공간에 직접 접근하여 개별 노드를 읽고 수정 가능
- 이 Human-Editable Latent Space가 Incurator의 핵심 가치

---

## 2. Encoder Pass: L1 → L2 Atom (잠재 공간 생성)

### 2.1. CTX section 마커 기반 Batch Extraction (구버전 naive 2K-char 분할 대체)

구버전 접근은 "섹션당 1 LLM 호출"이었다. v0.2.1에서는 **CTX 파일 전체를 1회 배치 호출**로
처리한다 (spec 08 섹션 2.1 참조). 섹션 컨텍스트는 별도 LLM 호출이 아니라
CTX 파일에 이미 삽입된 `<!-- section:id page:N -->` 마커로 보존된다.

**ToC 청킹의 새 역할**: 문서가 50K chars를 초과할 때 섹션 경계 기준으로
배치를 2-3개 그룹으로 나누는 데 사용. 섹션당 LLM 호출이 아님.

```python
MAX_BATCH_CHARS = 50_000  # spec 08 _split_into_batches()와 동일 상수

def group_sections_for_batch(ctx_path: str) -> list[str]:
    """
    CTX 파일 body를 MAX_BATCH_CHARS 이하의 그룹으로 묶어 반환.
    각 그룹에는 <!-- section:id page:N --> 마커가 그대로 포함되어 있어
    LLM이 source_section_id를 스스로 판단할 수 있다.

    문서 크기 <= MAX_BATCH_CHARS: 그룹 1개 (1 LLM call)
    문서 크기 > MAX_BATCH_CHARS: 섹션 경계 기준으로 2-3개 그룹
    """
    content = read_ctx(ctx_path)
    body = _ctx_body_only(content)  # frontmatter 제거, section 마커 포함 body
    return _split_into_batches(body, MAX_BATCH_CHARS)  # spec 08에서 구현
```

LLM은 배치 내 `<!-- section:s3 page:7 -->` 마커를 읽고 각 atom의 `source_section_id`를
판단한다 → 섹션 귀속 정확도를 per-section call과 동등하게 유지하면서 호출 횟수는 대폭 감소.

**섹션 마커가 없는 문서** (ToC 없는 arXiv 논문 등):
- `<!-- section:... -->` 마커 없이 plain text body만 전달
- LLM이 `source_section_id`를 빈 문자열로 채움
- `source_page`는 여전히 atom별로 기록되므로 HITL 원본 대조 가능

### 2.2. Atom frontmatter에 출처 메타데이터 필수 기록

```yaml
---
id: ATM-9f8e7d6c
type: atom
parent_source: "01_Contexts/CTX-a1b2c3d4"
source_section_id: "s3"        # L1 toc entry id
source_section_title: "2.1 Setup"
source_page: 5                  # 원본 PDF 페이지 번호
claim_type: fact                # fact | equation | entity | technique
confidence_score: 0.87
is_verified_by_human: false
---
```

`source_page`가 있어야 HITL 역전파 시 사용자가 원본 PDF와 대조 가능.

---

## 3. Decoder Pass: L2 → L3 → L4

### 3.1. L3 Concept 클러스터링 — 2단계 접근 *(구버전 미명시)*

소스가 쌓일수록 ATM 파일이 폭발적으로 증가한다. 한 번에 수천 개 Atom을 LLM에게 던지면
토큰 초과. **2단계 클러스터링** 필요:

**Step 1 — 로컬 클러스터링 (신규 소스 내부):**

```python
def cluster_atoms_local(new_atom_ids: list[str]) -> list[ConceptDraft]:
    """방금 추가된 소스의 Atom들끼리만 먼저 클러스터링 → 임시 Concept 초안"""
    atoms = [load_atom(a) for a in new_atom_ids]
    # LLM에게 이 소스 내에서 주제별로 묶으라고 요청
    return llm_cluster(atoms)
```

**Step 2 — 글로벌 병합 (기존 CON과 비교):**

```python
def merge_with_existing_concepts(drafts: list[ConceptDraft]) -> list[str]:
    """임시 Concept 초안을 기존 CON-*.md와 비교, 유사하면 병합"""
    existing = load_all_concepts()
    results = []
    for draft in drafts:
        best_match = find_most_similar(draft, existing, threshold=0.72)
        if best_match:
            merge_into_concept(best_match, draft)
            results.append(best_match.id)
        else:
            new_con = create_concept(draft)
            results.append(new_con.id)
    return results
```

이 방식으로 N개 소스가 쌓여도 LLM 호출 횟수는 `O(소스별 청크 수)`로 관리 가능.

### 3.2. L4 Exhibition: No Skip Connection 규칙

L4 생성 시 L1 원본을 **절대 접근하지 않는다**. 코드 레벨에서 강제:

```python
def generate_l4_exhibition(concept_ids: list[str], vault_path: str) -> str:
    # L3만 로드, CTX(L1) 경로는 쿼리에서 명시적으로 제외
    concepts = [load_concept(cid, vault_path) for cid in concept_ids]
    atoms = [load_atom(aid, vault_path)
             for cid in concept_ids
             for aid in get_concept_atom_ids(cid)]

    # concepts + atoms만 포함, CTX 내용 없음
    prompt = build_exhibition_prompt(concepts=concepts, atoms=atoms, raw_l1=None)
    return llm_synthesize(prompt)
```

`raw_l1=None` → 함수 시그니처 자체가 L1 접근 차단.

### 3.3. 증분 업데이트 프로토콜 *(구버전 완전 누락)*

새 소스 추가 시 기존 DAG 확장:

```
새 소스 추가
  → L2 Atom 생성 (신규)
  → 로컬 클러스터링 → 임시 CON 초안
  → 기존 CON과 유사도 비교
     → 유사 CON 발견: ATM을 기존 CON에 추가 + CON 재합성
     → 신규 CON 생성: 해당 CON을 참조하는 EXH 목록 확인 후 영향받는 EXH 재생성
  → DB에 영향받은 노드 목록 기록 (backprop 추적용)
```

---

## 4. 토큰 비용 추적 *(구버전 누락)*

`ingest_jobs` 테이블에 비용 컬럼 추가:

```sql
ALTER TABLE ingest_jobs ADD COLUMN input_tokens INTEGER DEFAULT 0;
ALTER TABLE ingest_jobs ADD COLUMN output_tokens INTEGER DEFAULT 0;
ALTER TABLE ingest_jobs ADD COLUMN estimated_cost_usd REAL DEFAULT 0.0;
```

`wiki status`에서 누적 비용 표시:

```
Sources: 15 (12 complete, 2 processing, 1 queued)
Total LLM cost: $2.43 (input: 1.2M tokens, output: 340K tokens)
```

---

## 5. L1 이미지 추출 — Scribbling 및 임베디드 이미지 지원

PDF 문서에는 텍스트 외에도 중요한 정보가 이미지 형태로 존재한다:
- 손으로 그린 다이어그램, 낙서(Scribbling)
- 형광펜/펜 주석이 포함된 스캔 페이지
- 논문 내 Figure, Graph, Algorithm 박스
- 손글씨 노트가 인쇄된 PDF

이것들을 무시하면 L1이 텍스트만 담은 불완전한 컨텍스트가 된다.

### 5.1. PyMuPDF 이미지 추출

PyMuPDF는 PDF 페이지 내 임베디드 이미지를 추출할 수 있다:

```python
# backend/src/curator/parsers/pdf_parser.py (확장)

import fitz  # PyMuPDF

def extract_page_images(doc: fitz.Document, page_num: int) -> list[dict]:
    """
    단일 페이지에서 임베디드 이미지 메타데이터 추출.
    실제 이미지 bytes는 필요 시에만 로드 (메모리 절약).
    """
    page = doc[page_num]
    image_list = page.get_images(full=True)  # (xref, smask, width, height, ...)

    results = []
    for img_info in image_list:
        xref = img_info[0]
        width, height = img_info[2], img_info[3]
        if width < 50 or height < 50:
            continue  # 너무 작은 이미지 (로고, 아이콘 등) 스킵

        base_image = doc.extract_image(xref)
        results.append({
            "xref": xref,
            "page": page_num,
            "width": width,
            "height": height,
            "ext": base_image["ext"],      # "png" | "jpeg" | "webp"
            "image_bytes": base_image["image"],
        })
    return results
```

### 5.2. 이미지 저장 경로

추출된 이미지는 vault의 `05_Assets/` 하위에 소스별 폴더로 저장:

```
05_Assets/
└── <source_slug>/      ← source 파일명에서 유도 (공백 → _, 특수문자 제거)
    ├── p03_img01.png   ← page_num + image index
    ├── p07_img01.jpeg
    └── p15_img01.png
```

```python
def _save_source_images(
    parsed_images: list[dict],
    source_slug: str,
    vault_root: Path,
) -> list[dict]:
    """이미지 저장 후 메타데이터 반환. CTX frontmatter에 포함."""
    assets_dir = vault_root / "05_Assets" / source_slug
    assets_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for img in parsed_images:
        filename = f"p{img['page']:02d}_img{img['xref']:04d}.{img['ext']}"
        dest = assets_dir / filename
        dest.write_bytes(img["image_bytes"])
        saved.append({
            "obsidian_path": f"05_Assets/{source_slug}/{filename}",
            "page": img["page"],
            "width": img["width"],
            "height": img["height"],
        })
    return saved
```

### 5.3. CTX frontmatter에 이미지 목록 포함

L1 Context 파일의 frontmatter에 `embedded_images` 배열로 기록:

```yaml
---
id: CTX-abc12345
type: context
source_path: "[[04_Resources/paper.pdf]]"
toc:
  - { id: "sec1", title: "Introduction", level: 1 }
  - ...
embedded_images:
  - { obsidian_path: "05_Assets/paper/p03_img01.png", page: 3 }
  - { obsidian_path: "05_Assets/paper/p07_img01.png", page: 7 }
  - { obsidian_path: "05_Assets/paper/p15_img01.jpeg", page: 15 }
content_hash: "a3f9b2c1"
last_updated: "2026-05-29"
---

# paper.pdf — Context

...text sections...

## Embedded Figures

![[05_Assets/paper/p03_img01.png]]
*Figure (p.3)*

![[05_Assets/paper/p07_img01.png]]
*Figure (p.7)*
```

CTX body 하단에 `![[...]]` 형식으로 삽입하면 Obsidian에서 즉시 시각화 가능.

### 5.4. L2 Atom 추출 시 이미지 활용

vision-capable LLM(agy Gemini Pro, Claude)을 사용하는 경우,
L2 batch extraction 프롬프트에 이미지를 함께 전달하여 scribbling도 Atom으로 추출:

```python
def run_l2_batch_extraction_with_images(
    paths: WikiPaths,
    client,
    document_text: str,
    image_paths: list[str],   # CTX embedded_images에서 읽음
    context_id: str,
    ...
) -> list:
    """
    vision-capable client면 이미지도 메시지에 포함.
    텍스트 전용 client면 image_paths 무시 (기존 텍스트만 추출).
    """
    content_parts = [{"type": "text", "text": _build_l2_prompt(document_text)}]

    if _supports_vision(client) and image_paths:
        for img_path in image_paths[:5]:   # 최대 5개 이미지 (토큰 한도)
            abs_path = paths.vault_root / img_path
            if abs_path.exists():
                img_b64 = base64.b64encode(abs_path.read_bytes()).decode()
                ext = abs_path.suffix.lstrip(".")
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{ext};base64,{img_b64}"}
                })

    messages = [ChatMessage(role="user", content=content_parts)]
    raw = client.chat(messages, json_mode=True, temperature=0.1)
    return _parse_batch_atoms_json(raw)


def _supports_vision(client) -> bool:
    """client가 vision 입력을 지원하는지 확인."""
    # AntigravityCliClient (Gemini), ClaudeCodeClient → vision 지원
    # OllamaClient → 모델에 따라 다름 (llava 등)
    from .llm import AntigravityCliClient, ClaudeCodeClient, OllamaClient
    if isinstance(client, (AntigravityCliClient, ClaudeCodeClient)):
        return True
    if isinstance(client, OllamaClient):
        # Ollama 모델명에 'vision', 'llava', 'bakllava' 포함 여부로 판단
        model_name = client.model or ""
        return any(k in model_name.lower() for k in ("vision", "llava", "bakllava"))
    return False
```

**텍스트 전용 LLM에서의 폴백**: 이미지를 전달할 수 없는 경우,
CTX body의 `![[...]]` 참조와 page 번호만 ATM의 `source_section` 필드에 기록.
사용자는 Obsidian에서 해당 ATM을 보며 이미지를 직접 확인할 수 있다.

### 5.5. 이미지 추출 비활성화 옵션

`.curator/config.yml`에서 제어:

```yaml
ingest:
  extract_images: true          # 기본값: true
  max_images_per_source: 20     # 과도한 이미지 PDF 방지 (기본: 20)
  min_image_size_px: 50         # 너무 작은 이미지 무시 (로고 등)
```

---

## 6. HITL 역전파 (Backpropagation)

### 5.1. 오차 신호 획득

사용자가 `02_Wiki/`의 L4 문서를 직접 수정 → 파일 hash 변경 → `wiki sync`가 감지.

### 5.2. 역전파 흐름

```
L4 수정 감지
  → Provenance 추적: EXH → CON → ATM
  → 문제 ATM 식별 (ATM의 source_page로 원본 PDF 대조 가능)
  → 영향받는 서브그래프 격리
  → is_verified_by_human=true인 노드는 건드리지 않음
  → 나머지만 LLM 재실행 (Incremental Rebuild)
```

### 5.3. `is_verified_by_human` 보호 로직

```python
def incremental_rebuild(node_id: str):
    fm = read_frontmatter(node_id)
    if fm.get("is_verified_by_human"):
        # 사람이 검증한 노드 보호 — 상위 노드만 재생성
        propagate_forward_from(node_id)
        return
    rebuild_node(node_id)
```

# 01. 아키텍처 심층 분석 (투트랙 L1 파이프라인 및 Fog of War 해소 전략)

본 명세서는 현재 Incurator 시스템이 겪고 있는 구조적 병목의 근본 원인을 해부하고,
최신 Agentic RAG 기술과 제텔카스텐 지식망의 철학을 결합한 **"투트랙(Two-Track) L1 추출
아키텍처"**를 심층 분석하는 연구 백서입니다.

---

## 1. 현재 시스템 (AS-IS): 동기식 Eager DAG 구조의 치명적 결함

### 1.1. 텍스트 파싱 파이프라인의 1차원적 문맥 유실

`ingest_raw.py`는 `pdfminer` 기반으로 PDF 텍스트를 추출한다.

- **레이아웃 파괴**: 논문의 다단(Two-column), 그림 캡션, 각주가 1차원 문자열로 뒤섞임
- **구조 상실**: 폰트 크기로 표현되던 계층 구조(Heading)가 사라져 LLM의 문맥 단서 제거
- **환각의 근본 원인**: 섹션 경계를 모르는 LLM은 무관한 단락들을 억지로 연결

### 1.2. 무지성 전체 추출과 동기 블로킹

- 50페이지 PDF를 2,000자 단위로 토막 내어 L2/L3를 순차적으로 추출 → 수십 분 소요
- 이 연산이 끝날 때까지 Obsidian 에이전트 UI가 완전히 멈춤 (UI Blocking)
- MCP 타임아웃으로 에러 처리되는 경우 빈번

---

## 2. 목표 시스템 (TO-BE): 투트랙(Two-Track) L1 파이프라인

### 2.1. Agent Viewer Mode — Fog of War 해소 + Adaptive Routing

#### Fog of War 문제

Obsidian PDF 뷰어는 Lazy Rendering 방식이라 에이전트가 즉시 접근 가능한 텍스트는
사용자 현재 **Viewport**에 해당하는 페이지뿐이다. 이것이 "전장의 안개(Fog of War)".

#### 해결: Minimap + Active Scouting Tool Calling

1. **Global ToC 주입**: 에이전트 시스템 프롬프트에 문서 전체 목차 트리를 경량 미니맵으로 상시 제공
2. **능동적 섹션 조회**: 에이전트가 미니맵을 보고 필요한 섹션을 판단, MCP 툴 직접 호출

**`fetch_document_section` 올바른 시그니처:**

```python
# ❌ 잘못된 설계:
# filepath가 절대경로/Zotero 경로 혼재, section_id를 에이전트가 알 수 없음
def fetch_document_section(filepath: str, section_id: str)

# ✅ 올바른 설계 (v0.2.1):
def fetch_document_section(
    source_key: str,      # logical_source_id (DB 기준, 기기/경로 독립적)
    toc_id: str = "",     # L1 frontmatter toc 배열에서 참조하는 section id
    page_start: int = 0,  # ToC 없을 때 페이지 범위 fallback
    page_end: int = 0,
) -> dict
```

- `source_key`는 `logical_source_id` — DB에 등록된 안정적 식별자, 기기/경로 독립적
- `toc_id`를 에이전트가 알 수 있는 이유: L1 frontmatter의 `toc` 배열에 id 목록 포함 (02번 명세 참조)
- ToC 없는 PDF를 위한 페이지 범위 fallback 필수

---

### 2.2. 두 가지 등록 경로 (Registration Paths)

문서가 Incurator에 등록되는 경로는 두 가지이며, 최종 결과(DB + CTX 파일)는 동일하다.

#### Path A — CLI (`wiki add`)

```
wiki add paper.pdf
  → PyMuPDF 파싱 (이미지 포함, spec 03 섹션 5)
  → CTX-UUID.md 생성 (Immutable Ground Truth)
  → state.sqlite에 file_hash + source_id 등록
  → ingest_jobs에 l2_atoms 큐잉 → IngestWorker 비동기 처리
  → 즉시 반환 ("L1 등록 완료. L2-L3 백그라운드 처리 중.")
```

#### Path B — Plugin (`import_source` MCP)

```
에이전트가 플러그인에서 import_source(source_key) 호출
  → 백엔드가 원본 파일을 PyMuPDF로 파싱 (Path A와 동일)
  → 이하 Path A와 동일 흐름
```

두 경로 모두 **파싱은 항상 백엔드 PyMuPDF**가 담당한다.
프론트엔드 PDF.js 파싱 결과(ephemeral)를 CTX 원본으로 쓰지 않는다.
이미지 추출, 폰트 기반 헤딩 감지 등은 서버사이드에서만 보장된다.

---

### 2.3. Adaptive Routing Protocol

**핵심 원칙**: 에이전트와 플러그인은 문서가 "어느 경로로 등록됐는지"를 알 필요가 없다.
`check_source_status(file_hash)` 한 번으로 현재 상태를 파악하고 자동 라우팅한다.

#### `check_source_status` MCP 툴

```python
def check_source_status(file_hash: str) -> dict:
    """
    파일 SHA256 hash로 등록 상태 조회.
    경로/기기가 달라도 동일 파일이면 같은 결과 반환.
    """
    row = db.find_source_by_hash(db_path, file_hash)
    if not row:
        return {"registered": False}

    pending_jobs = db.get_pending_jobs_for_source(db_path, row["id"])
    return {
        "registered": True,
        "source_id": row["id"],
        "l1_complete": row["ctx_id"] is not None,
        "l2_complete": not any(j["job_type"] == "l2_atoms" and
                               j["state"] in ("queued", "running")
                               for j in pending_jobs),
        "l3_complete": not any(j["job_type"] == "l3_concepts" and
                               j["state"] in ("queued", "running")
                               for j in pending_jobs),
        "jobs_pending": [{"type": j["job_type"], "state": j["state"]}
                         for j in pending_jobs],
    }
```

#### 플러그인 PDF 열기 시 자동 상태 감지

```
PDF 파일 열림 (externalPdfView.ts)
    ↓
file_hash = SHA256(file_bytes)
check_source_status(file_hash) 호출
    │
    ├── registered=False
    │       → ephemeral L1 모드 (PDF.js in-memory 파싱)
    │       → 플러그인 UI: "+ Add to Incurator" 버튼 표시
    │       → 에이전트 시스템 프롬프트: "문서 미등록. fetch_document_section으로 읽는 중."
    │
    ├── registered=True, l3_complete=False
    │       → ephemeral L1 모드 (처리 완료 전 임시)
    │       → 플러그인 UI: "⟳ Processing (L2/L3 백그라운드)" 상태 표시
    │       → 5초 간격 재폴링 → l3_complete=True 되면 자동 업그레이드
    │       → 에이전트 시스템 프롬프트: "처리 중. 현재 원문 직접 읽는 중."
    │
    └── registered=True, l3_complete=True
            → curator_query() 모드 (전체 knowledge graph)
            → 플러그인 UI: "✓ Indexed (47 atoms · 8 concepts)" 표시
            → 에이전트 시스템 프롬프트: "Incurator 지식 그래프 사용 가능."
```

#### 에이전트 시스템 프롬프트 자동 주입

플러그인이 PDF를 열 때 에이전트 컨텍스트에 문서 상태와 **현재 워크스페이스 컨텍스트**를 주입한다.
워크스페이스 컨텍스트는 `curator_check_workspace(workspace_path)` 호출 결과에서 파생되며,
`curator_query(question, workspace_id=...)` 호출 시 에이전트가 이 값을 그대로 전달한다.

```
[Incurator 문서 상태]
파일: paper_xyz.pdf
상태: ✓ Indexed
  - 47 atoms · 8 concepts · 2 exhibitions
  - 마지막 업데이트: 2026-05-29
현재 워크스페이스: transformer_paper
사용 가능한 도구: curator_query("질문", workspace_id="transformer_paper")

ToC (미니맵):
  1. Introduction (p.1)
  2. Background (p.3)
    2.1 Self-Attention (p.4)
  3. Method (p.7)
  ...
```

워크스페이스 컨텍스트가 없을 때 (워크스페이스 외부에서 PDF를 열거나, Vault 루트에서 작업 중):

```
[Incurator 문서 상태]
파일: paper_xyz.pdf
상태: ✓ Indexed
  - 47 atoms · 8 concepts · 2 exhibitions
현재 워크스페이스: (없음 — 기본값 "default" 사용)
사용 가능한 도구: curator_query("질문", workspace_id="default")
```

미등록 문서의 경우:

```
[Incurator 문서 상태]
파일: new_paper.pdf
상태: 미등록 (Incurator 지식 그래프 없음)
읽기 방법: fetch_document_section(source_key, toc_id)
등록하려면: import_source("new_paper.pdf")

ToC (미니맵):
  1. Introduction (p.1)
  ...
```

**workspace_id 해결 로직:**

```typescript
// plugin: externalPdfView.ts
function buildSystemPromptInjection(
    docStatus: SourceStatus,
    activeWorkspace: string | null,
): string {
    const workspaceId = activeWorkspace
        ? path.basename(activeWorkspace)  // "01_Workspaces/MyProject" → "MyProject"
        : "default";
    // ...
}
```

`workspace_id`는 워크스페이스 폴더 이름(slug)으로 결정된다.
에이전트가 `curator_check_workspace()`를 호출하면 반환값의 `workspace` 필드에서 slug를 얻는다.

#### `wiki add` CLI 경로와의 통합

`wiki add`는 플러그인 없이 터미널에서 실행되지만 **동일한 DB에 등록**된다.
이후 플러그인에서 같은 PDF를 열면 `check_source_status(hash)`가 "이미 등록됨"을 반환한다.
경로가 달라도(터미널에서 절대경로, 플러그인에서 vault 상대경로) hash 기반이라 동일하게 인식된다.

```
wiki add /home/shin/Downloads/paper.pdf  (터미널)
    → DB에 hash + CTX 등록
    → IngestWorker L2/L3 처리 중...

(다음 날 Obsidian에서 같은 파일 열기)
    → check_source_status(hash) → "registered, l3_complete=true"
    → 자동으로 curator_query() 모드로 라우팅
```

#### ephemeral L1 (`fetch_document_section`)의 실제 동작

미등록 문서 또는 L3 처리 중인 문서에서 `fetch_document_section`을 호출하면:
- 백엔드 호출 없음
- 플러그인이 PDF.js in-memory 파싱 결과에서 직접 해당 섹션 텍스트 반환
- 에이전트가 이 raw 텍스트를 직접 컨텍스트로 사용해 답변

```python
# 플러그인 측 (TypeScript) — MCP 요청을 intercept해서 직접 서빙
function handleFetchDocumentSection(source_key, toc_id, page_start, page_end) {
    const parsed = this.pdfState.getParsedDocument(source_key);
    if (!parsed) throw new Error("Document not open in viewer");

    if (toc_id) {
        return parsed.getSectionByTocId(toc_id);
    }
    return parsed.getPageRange(page_start, page_end);
}
```

등록된 문서에서 `fetch_document_section`을 호출하면:
- 백엔드 CTX 파일에서 해당 섹션을 반환 (더 정확한 PyMuPDF 파싱 버전)

---

### 2.3. ToC 없는 PDF를 위한 폴백 전략 *(구버전 플랜 누락)*

실제로 arXiv 논문 대부분이 ToC가 없다. 폴백이 없으면 Track 2의 ToC-guided chunking
전체가 무력화된다.

```python
def extract_document_structure(doc) -> list[TocEntry]:
    """ToC 우선, 없으면 폰트 크기 기반 헤딩 감지"""
    toc = doc.get_toc()
    if toc:
        return [TocEntry(level=t[0], title=t[1], page=t[2]) for t in toc]
    return _detect_headings_by_font_size(doc)

def _detect_headings_by_font_size(doc) -> list[TocEntry]:
    """
    fitz.Page.get_text("dict") → blocks → lines → spans
    본문 중앙값 폰트보다 1.2x 이상이면 헤딩으로 간주
    """
    font_sizes = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    font_sizes.append(span["size"])

    if not font_sizes:
        return []

    body_size = sorted(font_sizes)[len(font_sizes) // 2]
    headings = []
    for page_num, page in enumerate(doc):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                max_size = max(s["size"] for s in spans)
                if max_size >= body_size * 1.2:
                    title = "".join(s["text"] for s in spans).strip()
                    level = 1 if max_size >= body_size * 1.5 else 2
                    headings.append(TocEntry(level=level, title=title, page=page_num + 1))
    return headings
```

**폴백 계층:**
1. `doc.get_toc()` — 문서 내장 ToC
2. 폰트 크기 분석 — 시각적 헤딩 감지
3. 정규식 `^\d+\.\s` 패턴 매칭 — 번호 매긴 섹션 감지
4. 단락 길이 기반 단순 분할 — 완전 fallback

---

## 3. 구현 시퀀스 (의존성 기반, 구버전 Phase 1→5 순서 수정)

기존 플랜의 Phase 1→2→3→4→5 순서는 의존성을 무시한 순서다.

```
P0 (기반): PyMuPDF + ToC 추출 + 폴백 전략 [Phase 2 핵심]
           없으면 Phase 4 전체 불가
           ↓
P1 (독립): Fog of War MCP 도구 [Phase 1]    ← P0과 병렬 가능
           빠른 UX 개선, 독립적 deliverable
           ↓
P2 (인프라): MCP 내장 워커 스레드 [Phase 3 수정]
           없으면 P3가 여전히 동기 블로킹
           ↓
P3 (핵심가치): ToC-guided 청킹 + 비동기 파이프라인 [Phase 4]
           양질의 L2가 있어야 역전파가 의미있음
           ↓
P4 (품질보증): HITL 양방향 역전파 [Phase 5 수정]
```

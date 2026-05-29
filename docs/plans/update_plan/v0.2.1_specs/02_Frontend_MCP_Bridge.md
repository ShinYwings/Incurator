# 02. 구조적 주입 브릿지: 프론트엔드 & 백엔드 파싱

본 명세서는 백엔드의 낡은 `pdfminer` 파싱으로 인한 텍스트 훼손 문제를 해결하고,
에이전트(MCP)와 터미널(`wiki add`) 환경 모두에서 완벽한 구조적 주입(Structural Injection)을
달성하기 위한 기술 명세입니다.

---

## 1. 프론트엔드 네이티브 파싱 (`externalPdfView.ts`) — Agent Track

에이전트가 문서를 열 때, 백엔드의 무거운 파싱 과정을 바이패스한다.

### 1.1. PDF.js Native API 연동

```typescript
// pdf.getOutline() → ToC 트리 객체 (문서 작성자가 심어둔 목차)
const outline = await pdf.getOutline();

// getTextContent() → 텍스트 + 뷰포트 좌표 + 페이지 번호
const textContent = await page.getTextContent();
```

### 1.2. DOM 및 A11y 매핑 (HTML/MD)

HTML/MD 문서는 화면에 렌더링된 요소의 `className`과 시맨틱 태그(`h1~h6`)를 분석하여
논리적 계층을 매핑한다.

---

## 2. 백엔드 네이티브 파싱 (`ingest_raw.py`) — CLI Track

사용자가 터미널에서 `wiki add` 명령을 실행할 때도 프론트엔드와 동일한 품질의 파싱 보장.

### 2.1. PyMuPDF (fitz) 도입

낡은 `pdfminer`를 폐기하고 `PyMuPDF`를 도입한다.

```python
import fitz

doc = fitz.open(filepath)
toc = doc.get_toc()  # [[level, title, page], ...]
# 프론트엔드 pdf.js의 getOutline()과 동일한 구조
```

### 2.2. MD / HTML 파싱

```python
# MD: # 개수 카운트
import re
md_headings = re.findall(r'^(#{1,6})\s+(.+)$', text, re.MULTILINE)

# HTML: BeautifulSoup h1~h6 순회
from bs4 import BeautifulSoup
soup = BeautifulSoup(html, 'html.parser')
headings = soup.find_all(['h1','h2','h3','h4','h5','h6'])
```

---

## 3. L1 파일 포맷 *(구버전의 `<h2 id="...">` 방식은 폐기)*

### 3.1. 구버전의 문제점

```markdown
<!-- ❌ 구버전: HTML 태그 직접 삽입 -->
[Page 4]
<h2 id="toc-2-methodology">2. Methodology</h2>
Methods text...
```

- Obsidian이 `<h2>` 태그를 HTML로 렌더링 → 노트 표시 오염
- LLM이 HTML 태그를 불필요한 노이즈로 처리
- VaultPathSuggest autocomplete와 충돌 가능

### 3.2. 올바른 포맷 — YAML frontmatter + 마크다운 헤더 + HTML 주석

```markdown
---
id: CTX-a1b2c3d4
type: context
source_path: "04_Resources/paper.pdf"
source_hash: "sha256:abc..."
toc:
  - {id: "s1", level: 1, title: "Introduction", page: 1}
  - {id: "s2", level: 2, title: "1.1 Background", page: 2}
  - {id: "s3", level: 1, title: "Methodology", page: 4}
  - {id: "s4", level: 2, title: "2.1 Setup", page: 5}
last_updated: "2026-05-28T10:00:00Z"
---

<!-- section:s1 page:1 -->
## Introduction

...텍스트...

<!-- section:s3 page:4 -->
## Methodology

...텍스트...
```

- `toc` YAML 배열 → 에이전트가 `toc_id` 목록 파악, `fetch_document_section` 호출 근거
- 본문은 표준 마크다운 헤더 (`##`) → Obsidian 렌더링 정상
- `<!-- section:id page:N -->` HTML 주석 → 섹션 경계 마커, 렌더링에 영향 없음

### 3.3. 섹션 추출 로직

`fetch_document_section(source_key, toc_id="s3")`가 호출되면:

```python
def _extract_section_by_toc_id(ctx_content: str, toc_id: str) -> str:
    """<!-- section:s3 ... --> 마커를 기준으로 해당 섹션 텍스트 추출"""
    pattern = rf'<!-- section:{re.escape(toc_id)}[^>]*-->(.*?)(?=<!-- section:|$)'
    match = re.search(pattern, ctx_content, re.DOTALL)
    return match.group(1).strip() if match else ""
```

---

## 4. MCP Payload — ephemeral viewer 전용

**중요**: 이 payload는 `fetch_document_section` 호출 시 플러그인이
ephemeral L1(in-memory)에서 섹션 텍스트를 서빙하는 데만 사용된다.
**CTX 파일 생성(`import_source`, `wiki add`)에는 사용하지 않는다.**

CTX 파일은 항상 백엔드 PyMuPDF가 직접 파싱하여 생성한다 (spec 01 섹션 2.2).
이미지 추출, 폰트 기반 헤딩 감지 등 서버사이드 품질 보장이 필요하기 때문이다.
v0.2.1 구현에서는 `llm.instant_l1: true`가 기본값이며, `wiki add`/`import_source`
직후 LLM 호출 없이 parser 구조만으로 CTX를 즉시 생성한다. 이 CTX는 `toc`,
`<!-- section:sN page:P -->` marker, `Source Sections`, coarse `Atom Candidates`를
포함하고, L2/L3 추출은 background job으로 이어진다. 레거시 LLM 기반 L1 요약이
필요하면 `.curator/config.yml`에서 `llm.instant_l1: false`로 끌 수 있다.

```json
{
  "source_key": "file_hash_or_path",
  "toc_tree": [
    {"id": "s1", "level": 1, "title": "Introduction", "page": 1},
    {"id": "s2", "level": 2, "title": "1.1 Background", "page": 2}
  ],
  "structural_content": "<!-- section:s1 page:1 -->\n## Introduction\n\n...text..."
}
```

`structural_content`는 플러그인이 `fetch_document_section(source_key, toc_id="s1")`
요청을 받았을 때 백엔드를 거치지 않고 즉시 해당 섹션을 서빙하기 위한
**in-memory 캐시**다.

### 4.1. fetch_document_section 서빙 경로

```
fetch_document_section(source_key, toc_id) 호출
    ↓
문서가 등록됐나? (check_source_status)
    │
    ├── 미등록
    │     → 플러그인 in-memory (structural_content)에서 직접 서빙
    │     → 백엔드 미호출
    │
    ├── 등록됨 + L1 complete + L2/L3 처리 중
    │     → 백엔드 CTX Source Sections에서 section marker 기준 서빙
    │     → curator_query는 아직 제한됨
    │
    └── 등록 완료 (L3 complete)
          → 백엔드 CTX 파일에서 _extract_section_by_toc_id() 서빙
          → PyMuPDF 파싱 버전 (더 정확)
```

---

## 5. 파싱 우선순위 결정 로직 (CTX 파일 생성 시)

`import_source` 또는 `wiki add` 경로에서 CTX 파일을 생성할 때:

```
source_key로 원본 파일 접근
    → PDF? PyMuPDF로 파싱 (이미지 포함, spec 03 섹션 5)
    → MD? 정규식 헤딩 파싱
    → HTML? BeautifulSoup 파싱
```

Zero-Ingest(프론트엔드 structural_content 재사용)는 CTX 생성에 적용하지 않는다.

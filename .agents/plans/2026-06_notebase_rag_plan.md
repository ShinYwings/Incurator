# Incurator Math-Aware Notebase RAG Revamp (v0.2.2)

이 문서는 Incurator의 RAG 시스템을 Cursor가 코드베이스를 읽는 수준으로 수학 수식(Math/LaTeX)과 학술 노트를 완벽하게 이해할 수 있도록 개편하기 위한 아키텍처 개선 계획입니다.

## User Review Required

> [!IMPORTANT]  
> **파서(Parser) 도입 결정**
> 현재의 `pypdf`는 텍스트를 단순 추출하므로 논문의 수식과 표 레이아웃이 완전히 깨집니다. 이를 해결하기 위해 어떤 방식을 주력으로 사용할지 결정이 필요합니다:
> 1. **`pymupdf4llm` (권장/빠름)**: 로컬 기반이며 기존 `pymupdf(fitz)`를 활용해 PDF를 Markdown으로 변환합니다. 빠르고 가볍지만, 이미지로 렌더링된 복잡한 수식은 OCR에 한계가 있을 수 있습니다.
> 2. **`marker-pdf` (정확함/무거움)**: 딥러닝 기반으로 PDF를 완벽한 수식이 포함된 Markdown(LaTeX)으로 변환합니다. 품질은 최고지만 GPU/메모리 요구량이 큽니다.
> 3. **VLM (Vision API) 파서**: 문서의 페이지를 이미지로 렌더링한 후, LLM(Claude 3.5 Sonnet / GPT-4o Vision 등)에게 넘겨 Markdown으로 변환하게 하는 방식입니다.
> 
> **질문:** 로컬 환경 제약을 고려할 때, `pymupdf4llm`을 기본으로 도입하고 필요시 VLM/Marker를 선택할 수 있게 구조화하는 방향이 괜찮으신가요? (원하시는 방향을 답변해주세요)

## Open Questions

> [!WARNING]
> **마크다운 청킹(Chunking) 전략**
> 수학 수식 블록 (`$$...$$`)이 청킹 과정에서 잘리면 RAG 검색 및 L2 추출 시 치명적인 오류가 발생합니다. 코드베이스 청커처럼 Markdown AST를 분석하여 수식 블록을 보호하도록 `text.py`와 `ingest_raw.py`를 수정할 계획입니다. Obsidian 노트에 작성하시는 수식은 주로 표준 `$$` 문법을 사용하시나요? 

## Proposed Changes

현재 구조의 가장 큰 문제점(부족한 부분)은 **1) 파서의 한계(pypdf)** 와 **2) 수식 블록을 보호하지 않는 평문 기반 청킹**에 있습니다. L1 Context에 깨진 수식이 들어가면, L2/L3 모델이 아무리 똑똑해도 `claim_type: equation`으로 올바르게 추출할 수 없습니다.

---

### 1. docs/ (Architecture Source of Truth)

버전 관리를 위해 v0.2.2 스키마 스펙을 신설하고 관련 문서를 업데이트합니다.

#### [NEW] [SCHEMA_v0.2.2.md](file:///Users/shin/shinywings/Incurator/docs/specs/curator_schema/SCHEMA_v0.2.2.md)
- 기존 v0.2.1 스키마를 상속하되, L1 Context 생성 시 **Math-Aware Markdown Chunking** 규칙을 강제하는 명세 추가.
- `metadata`에 파서 타입 (`parser: pymupdf4llm` 등) 명시.

#### [MODIFY] [WORKFLOW_GUIDE_KR.md](file:///Users/shin/shinywings/Incurator/docs/guides/WORKFLOW_GUIDE_KR.md)
- PDF 및 MD 파싱 워크플로우에 Math-Markdown 변환 단계와 수식 블록 보호(Chunking) 내용 추가.

---

### 2. backend/pyproject.toml (Dependencies)

새로운 파서 라이브러리를 추가합니다.

#### [MODIFY] [pyproject.toml](file:///Users/shin/shinywings/Incurator/backend/pyproject.toml)
- `pypdf` 의존성을 줄이고, `pymupdf4llm` (또는 `pymupdf`) 의존성 추가.

---

### 3. backend/src/curator/parsers/ (Extraction Layer)

가장 핵심적인 변경 사항입니다. 단순 텍스트가 아닌 Markdown(LaTeX 포함)을 출력하도록 파서를 전면 교체합니다.

#### [MODIFY] [pdf.py](file:///Users/shin/shinywings/Incurator/backend/src/curator/parsers/pdf.py)
- `pypdf` 기반 텍스트 추출을 `pymupdf4llm` 기반 Markdown 추출로 교체.
- PDF의 표적 수식 영역이나 다단 레이아웃을 최대한 Markdown으로 보존하도록 파이프라인 리팩토링.

#### [MODIFY] [text.py](file:///Users/shin/shinywings/Incurator/backend/src/curator/parsers/text.py)
- Markdown 문서를 파싱할 때, `$$...$$` 형태의 LaTeX 블록과 Code 블록의 경계를 인식하여, L1 Context로 쪼개질 때 수식이 중간에 잘리지 않도록 (AST 기반 또는 정규식 기반) 안전한 분할 로직 추가.

---

### 4. backend/src/curator/ (Ingestion & RAG)

#### [MODIFY] [ingest_raw.py](file:///Users/shin/shinywings/Incurator/backend/src/curator/ingest_raw.py)
- `parsers`에서 넘어온 Markdown 데이터를 L1 Context로 변환 시, 수식 블록을 온전히 보존하도록 청킹 로직 개선.

## Verification Plan

### Automated Tests
- `pytest`에 수학 기호와 수식이 포함된 샘플 PDF 및 Markdown 노트를 처리하는 테스트 픽스처(`test_math_parsing.py`) 추가.
- `$$` 블록이 L1 Context 경계에서 잘리지 않는지 검증하는 단위 테스트 작성.

### Manual Verification
- 활성화된 `Multiple_View_Geometry_in_Computer_Vision-EN.pdf` (매우 수식이 많은 CV 서적) 문서를 대상으로 파싱 및 RAG 추출(`wiki add`)을 실행하여, L2 Atom으로 수식(`claim_type: equation`)이 깨지지 않고 LaTeX로 정확히 떨어지는지 Obsidian Viewer로 확인.

# [v0.2.1] Reference Mode RAG Architecture & Testbed Validation Plan

## Goal
Zotero 등의 외부 리소스(PDF)를 Vault 내부에 물리적으로 복사하지 않고도(Reference Mode), RAG 파이프라인(Curator)이 이를 완벽히 이해하고 테스트할 수 있도록 아키텍처를 구현하고 Testbed를 통해 이를 검증합니다.

## 인터뷰(/grill-me) 결과 요약
사용자와의 인터뷰를 통해 다음과 같은 핵심 설계 방향이 결정되었습니다.
1. **Testbed Mocking**: `scripts/dev/` 내에 가상의 Zotero 디렉토리를 생성하여, Testbed 환경이 이를 참조하도록 구성.
2. **Vault Representation**: `04_Resources/` 내에 외부 파일을 가리키는 Markdown Stub 파일을 생성하고, YAML Frontmatter에 `zotero_key` 또는 `target_path`를 기록.
3. **Backend Transparent Redirect**: 백엔드(`ingest_raw.py` 등)가 Markdown Stub을 읽을 때 Frontmatter를 파싱하여, 실제로는 외부 PDF 파일을 투명하게 파싱하도록 리다이렉트.

## User Review Required
> [!IMPORTANT]
> `docs/specs/curator_schema/SCHEMA_v0.2.1.md` 에 Reference Mode Markdown Stub에 대한 Frontmatter 스키마 규칙(`zotero_key`, `target_path` 필드 등)을 추가할 예정입니다. 또한 이 계획 문서는 승인 후 `.agents/plans/2024-05_v0.2.1_update/reference_mode_rag_plan.md`에도 영구 보존됩니다.

## Proposed Changes

### 1. Testbed & Mock Environment
#### [NEW] `scripts/dev/mock_zotero_env/`
- 가상의 Zotero 디렉토리 구조 생성 (`storage/TESTKEY1/mock_paper.pdf`)
- `wiki testbed init` 스크립트 수정 시, `ZOTERO_BASE_PATH` 환경 변수가 이 디렉토리를 가리키도록 설정 추가.

### 2. Backend (Transparent Redirect)
#### [MODIFY] `backend/src/curator/ingest_raw.py`
- RAG 파이프라인이 파일을 읽어들일 때 파일 확장자가 `.md`인 경우, Frontmatter를 먼저 파싱합니다.
- `zotero_key`가 존재하면 `zotero.py`의 `resolve_zotero_attachment_path`를 호출하여 실제 PDF 절대 경로를 찾고, 해당 PDF를 PyMuPDF로 파싱합니다.
- `target_path`가 존재하면 그 경로의 파일을 파싱합니다.

#### [MODIFY] `backend/src/curator/mcp_server.py`
- `fetch_document_section` 등 MCP 도구에서도 Stub 파일을 만나면 동일하게 실제 PDF의 텍스트를 반환하도록 투명한 리다이렉트 로직을 적용합니다.

### 3. Documentation & Specs
#### [MODIFY] `docs/specs/curator_schema/SCHEMA_v0.2.1.md`
- "Markdown Stub for External Resources"에 대한 스키마 정의 추가.
- 필수 Frontmatter (`type: reference`, `zotero_key`, `target_path`) 명시.

#### [NEW] `.agents/plans/2024-05_v0.2.1_update/reference_mode_rag_plan.md`
- AGENTS.md 규정에 따라 본 계획을 히스토리 보존용으로 커밋.

## Verification Plan

### Automated Tests (Testbed)
1. `VAULT_ROOT=testbed ZOTERO_BASE_PATH=scripts/dev/mock_zotero_env wiki ingest 04_Resources/mock_stub.md` 실행.
2. `wiki query`를 통해 가상의 Zotero PDF 내에 있는 내용을 정상적으로 RAG 검색하고 대답할 수 있는지 확인.
3. `pytest backend/tests/` 를 통해 Transparent Redirect 관련 단위 테스트 통과 확인.

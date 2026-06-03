# 🔌 MCP 사용법 가이드: 에이전트 연결하기


**Incurator MCP 서버**는 아티스트(인간 + 에이전트)가 큐레이터와 직접 상호작용하는 인터페이스입니다. Claude Desktop, Claude Code, Antigravity 등 워크스페이스 내의 에이전트는 이 MCP 서버를 통해 큐레이터가 준비한 전시물(Exhibition)을 탐색하고, 대화 중 발견한 오류나 새로운 인사이트를 사전 지식에 즉시 반영할 수 있습니다. 이를 통해 아티스트의 피드백이 지식 그래프로 전파되어 사전 지식이 교정되는 순환 구조가 완성됩니다.

[English Guide](MCP_USER_GUIDE.md)

---

## 1. 사전 요구 사항

MCP 의존성 패키지가 설치되어 있는지 확인하세요.
```bash
cd backend
uv pip install -e '.[mcp]'
```

> [!NOTE]
> 서버는 `VAULT_ROOT` 환경 변수를 참조하여 저장소 위치를 찾습니다. 에이전트/플러그인 연동에서는 가능한 한 항상 명시적으로 설정하세요. v0.2.0 계약에서는 잘못된 경로를 조용히 현재 디렉토리로 fallback하지 않고 명시적으로 실패하는 방향을 기준으로 합니다.

---

## 2. 클라이언트 설정

사용 중인 클라이언트에 맞는 설정 스니펫을 가져오려면 다음 명령어를 실행하세요.
```bash
wiki mcp install
```
특정 클라이언트를 지정할 수도 있습니다: `wiki mcp install claude` 또는 `wiki mcp install antigravity`.

### 설정 예시 (`mcp_config.json` 또는 `settings.json`)
```json
{
  "mcpServers": {
    "Incurator": {
      "command": "/절대/경로/wiki",
      "args": ["mcp"],
      "env": {
        "VAULT_ROOT": "/저장소/절대/경로"
      }
    }
  }
}
```

> [!TIP]
> 기기 간 동기화를 사용하는 경우 `command` 항목의 경로가 Linux와 macOS 환경에서 서로 다를 수 있습니다. 각 기기의 환경에 맞는 실행 파일 절대 경로를 지정하세요.

---

## 3. 주요 도구(Tools) 소개

### 3.1 검색 및 탐색

#### `search_curator`
- **역할**: QMD 엔진(BM25 + Vector + Rerank)을 사용하여 저장소 전체를 검색합니다.
- **자동 동기화**: 대기 중인 소스가 있으면 검색 전 자동으로 `wiki curate`를 실행합니다.
- **파라미터**: `query`, `scope` (contexts/atoms/concepts/exhibitions), `mode`, `limit`.

#### `curator_layer_index`
- **역할**: 각 레이어별 페이지 수와 최근 노드 샘플을 확인하여 저장소의 전반적인 상태를 파악합니다.

#### `curator_status`
- **역할**: 저장소 경로 및 검색 엔진 준비 상태를 확인합니다.

### 3.2 DAG 분석 및 순회

#### `curator_get_node`
- **역할**: 노드 ID(예: `EXH-abc12345`)를 통해 해당 마크다운의 전체 내용을 가져옵니다.

#### `curator_traverse_evidence`
- **역할**: Exhibition 노드를 기준으로 하위 Concept 및 Atom으로 이어지는 전체 증거 체인을 조회하여 주장을 검증합니다.

#### `curator_find_contradictions`
- **역할**: 인간의 검토가 필요하거나 모순되는 주장이 포함된 Atom 목록을 조회합니다.

### 3.3 지식 관리 및 업데이트

#### `curator_import_source`
- **역할**: Zotero 등 외부 디렉토리의 파일을 Incurator backend에 등록합니다. 정책에 따라 파일을 복사하지 않는 Reference Mode로 연결하거나, 사용자가 승인한 `04_Resources/` 목적지로 안전하게 복사할 수 있습니다.
- **파라미터**: 구현 단계에 따라 `file_path` 또는 `source_path`가 입력 이름으로 사용될 수 있습니다. 둘 다 외부 파일의 절대 경로를 의미합니다. 정책 필드는 `policy="reference"` 또는 `destination_policy="mirror_03_to_04"`처럼 명시합니다. 실제 클라이언트는 먼저 `dry_run=true`로 제안 결과를 받은 뒤 사용자 승인 후 mutation을 호출해야 합니다.
- **목적지 규칙**: 외부 PDF의 기본값은 Reference Mode입니다. backend는 `04_Resources/` 아래에 markdown reference stub을 만들고 PDF 원본은 기존 위치에 둡니다. Copy mode는 명시적으로 선택할 때만 사용하며, 이 경우에도 목적지는 `03_Notes`가 아니라 `04_Resources`입니다.
- **덮어쓰기 금지**: 동일 해시 파일은 기존 source를 재사용하고, 같은 이름이지만 다른 해시인 파일은 suffix 또는 사용자 선택 목적지를 사용해야 합니다.

#### `curator_register_source`
- **역할**: 깊은 LLM 처리 없이 구조 기반으로 소스를 빠르게 등록(L1 생성)합니다.
- **파라미터**: `file_path` 또는 `source_path`.
- **참고**: deprecated된 `curator_ingest_source`의 동기적 실행 부분을 대체합니다.

#### `curator_build_source`
- **역할**: 등록된 소스에 대해 깊이 있는 L2 (Atoms) 및 L3 (Concepts) 지식 추출 프로세스를 트리거합니다.
- **파라미터**: `file_path` 또는 `source_id`.

#### `curator_add_all`
- **역할**: 워크스페이스 source 디렉터리 전체에 대해 `wiki add`를 실행하여 새 파일이나 변경 파일을 발견하고 구조적 등록(L1)을 최신 상태로 유지합니다.
- **결과**: `discovered`, `removed`, `summarized` 카운트를 반환합니다.

#### `curator_build_all`
- **역할**: 대기 중인 작업이 있는 워크스페이스 내 모든 소스에 대해 깊이 있는 L2 및 L3 지식 추출 프로세스를 트리거합니다.

#### `curator_sync`
- **역할**: 지식 그래프 DAG를 동기화합니다. 변경된 노드를 식별하고 영향을 받는 하위 캐시 및 작업을 점진적으로 무효화합니다.

#### `curator_lint`
- **역할**: 워크스페이스 DAG에 대한 유효성 및 상태 검사를 수행하여 스키마 및 링크 무결성을 보장합니다.

#### `curator_ingest_source` (Deprecated)
- **역할**: 기존의 통합된 ingestion 도구입니다. 대신 `curator_register_source`와 `curator_build_source`를 사용하세요.

#### `curator_list_external_resources`
- **역할**: 플랫폼별 글로벌 설정(`~/.config/curator/config.yml`)에 정의된 외부 라이브러리(예: Zotero) 목록과 현재 활성화된 절대 경로를 반환합니다.

#### `curator_source_status`
- **역할**: 파일의 처리 상태 및 외부 경로(`external_path`) fallback 로직 상태를 조회합니다. 위치가 이동되어 `MOVED` 상태인 파일들을 식별할 수 있습니다.
- **파라미터**: `source_id`, `logical_source_id`, `source_path`, 또는 `file_path` 중 구현이 지원하는 식별자를 사용합니다.
- **Obsidian 플러그인 표시**: 플러그인은 이 결과를 PDF chip의 상태 badge로 표시할 수 있습니다. 예: `untracked`, `queued`, `running L1`, `running L2`, `running L3`, `running L4`, `l3_ready`, `l4_ready`, `stale`, `moved`, `error`.

#### `curator_rebind_source`
- **역할**: 외부 참조 파일의 해시가 변동(Hash Drift)되거나 물리적 위치가 이동된 경우, 인간의 승인을 거쳐 새로운 경로와 해시로 식별자(`logical_source_id`)를 리바인딩(Healing)합니다.
- **파라미터**: `logical_source_id` (고유 식별자), `new_path` (새로운 절대 경로).
- **주의**: 이 도구는 반드시 Human-in-the-Loop 승인 뒤에 호출되어야 합니다. backend는 제안과 실행을 구분해야 하며, client는 어떤 파일이 어떤 logical source로 묶이는지 사용자에게 보여줘야 합니다.

#### `curator_search_sources`
- **역할**: 특정 source 또는 PDF 페이지 범위 안에서만 검색합니다. Obsidian 플러그인이 현재 열린 PDF 질문을 backend RAG 결과와 결합할 때 사용합니다.
- **파라미터**: `query`, `source_id` 또는 `source_path`, 선택적으로 `page_start`, `page_end`, `limit`, `mode`.
- **반환값**: page number, score, snippet, source provenance를 포함해야 합니다.
- **참고**: 이전의 단수형 alias `curator_search_source`는 v0.2.1에서 제거되었습니다.

#### `curator_get_source_page`

- **역할**: backend가 파싱한 특정 source page의 text/provenance를 반환합니다. PDF 페이지 및 비-PDF 소스 모두 지원합니다.
- **파라미터**: `source_id` 또는 `source_path`, `page`.
- **용도**: plugin viewer context가 일시적으로 부족하거나 provider가 이미지 첨부를 무시하는 경우에도 텍스트 기반 컨텍스트를 안정적으로 보강합니다.
- **참고**: 이전의 alias `curator_get_pdf_page`는 v0.2.1에서 제거되었습니다.

#### `curator_get_pdf_context`

- **역할**: 채팅 컨텍스트용 경량 온디맨드 PDF 텍스트 추출. **인덱싱된 PDF와 인덱싱되지 않은 PDF 모두 지원** — 사전 ingestion 불필요. Obsidian 플러그인이 LLM 프롬프트의 `<pdf_window>`, `<document_outline>` 컨텍스트 블록을 조립할 때 사용하는 기본 툴.
- **파라미터**:
  - `file_path` (필수): PDF의 절대 경로.
  - `query` (선택): 관련도 기반 페이지 스코어링에 사용할 쿼리 문자열.
  - `page_num` (선택, 기본값 0): 현재 페이지 번호(1-based). 0 = 현재 페이지 없음.
  - `radius` (선택, 기본값 2): `page_num` 주변에 포함할 페이지 수.
  - `max_pages` (선택, 기본값 8): 최대 반환 페이지 수.
- **반환값**:
  - `ok`: 성공 시 `true`, 오류 시 `false`.
  - `source_tracked`: PDF가 Incurator 지식 그래프에 등록되어 있는지 여부.
  - `total_pages`: 전체 페이지 수.
  - `pages`: `[{page_num, text, score}]` — 최대 `max_pages`개의 관련 페이지.
  - `outline`: `[{title, page_num, level}]` — 문서 목차.
  - `is_empty_pdf`: 텍스트 추출 불가(스캔/이미지 전용) 시 `true`.
- **기존 문제 해결**: 이전에 플러그인은 `pdf_window`, `document_outline`, `pdf_rag_hits` 세 가지 MCP 호출을 했는데 모두 backend에 없어서 silent fail했음. 이 툴이 하나의 호출로 통합.
- **성능**: `parse_page_window()`로 필요한 페이지만 읽어 600페이지 PDF도 전체 메모리 로드 없이 안전하게 처리.

#### `curator_add_knowledge`
- **역할**: 대화 중 얻은 귀중한 통찰이나 정보를 **Wiki(02_Wiki/)** 페이지로 승격하여 영구 저장합니다. 카테고리 분류와 슬러그 생성이 자동으로 수행됩니다.

#### `curator_update_node`
- **역할**: **Exhibition (EXH)** 노드의 내용을 덮어씁니다. L1/L2/L3 노드에 대한 직접 수정은 백엔드의 DAG 파이프라인 무결성 유지를 위해 거부됩니다.
- **자동 수정 (Backprop)**: **Exhibition (EXH)** 노드를 수정할 경우, 백엔드 내부에서 `wiki sync`가 트리거되어 Concept, Atom, Context까지 변경 사항을 전파합니다. insight backprop은 드물게 발생하는 정정 경로이므로 단일 호출 latency보다 그래프 정합성을 우선합니다. 백엔드는 이전 Exhibition과 수정된 Exhibition의 텍스트 차이를 비교해 새 insight와 가장 관련 있는 Concept을 먼저 고르고, 가능한 경우 실제 변경이 필요한 Concept만 하나의 structured batch LLM 호출로 조정한 뒤, 실제로 상위 노드가 바뀐 경우에만 L2/L1로 내려갑니다. 변경이 없는 Concept은 batch 응답에서 생략할 수 있어 모델 출력 latency를 줄입니다. L1 업데이트는 원본 source truth를 보존하면서 derived correction을 별도로 기록해야 합니다. 명시적인 Concept-only dry run이나 진단 경로에서만 `propagate_sources=false`를 전달하세요.
- **No-op 보호**: 동일한 EXH 내용을 다시 제출하면 `noop=true`, `updated=false`, `propagation.llm_calls=0`을 반환하고, 백엔드는 routing table rebuild나 LLM 호출을 수행하지 않습니다.

#### `curator_reindex`
- **역할**: QMD 검색 인덱스를 수동으로 다시 빌드합니다.
- **Degraded result**: BM25 indexing은 성공했지만 vector embedding이 실패하면 `ok=true`, `updated=true`, `embedded=false`, `degraded=true`를 반환합니다. 이 상태에서는 lexical search는 최신이고 vector search만 stale입니다.

### 3.4 문서 상태 및 On-demand 쿼리 (v0.2.1)

#### `check_source_status`

- **역할**: 파일의 SHA-256 해시로 Incurator 등록 상태를 조회합니다. 플러그인이 PDF를 열 때 자동 호출하여 에이전트가 어느 모드(ephemeral / curator_query)로 작동해야 할지 결정합니다.
- **파라미터**: `file_hash` (파일 SHA-256 해시 문자열).
- **반환값**: `registered`, `source_id`, `l1_complete`, `l2_complete`, `l3_complete`, `jobs_pending`.
- **구현 상태**: 백엔드는 `sources.content_hash`를 조회하고 queued/running `ingest_jobs`를 함께 반환합니다.
- **참고**: 경로가 달라도(터미널 절대경로 vs 플러그인 상대경로) 동일 해시면 같은 결과를 반환합니다. `wiki add` CLI 경로와 플러그인 경로가 투명하게 통합됩니다.

#### `fetch_document_section`

- **역할**: 문서의 특정 섹션 텍스트를 반환합니다. 문서가 미등록이면 플러그인 in-memory(PDF.js)에서 서빙하고, `wiki add`/`import_source` 이후 `l1_complete=True`가 되면 백엔드는 CTX section id, 원본 heading, 또는 PDF page range로 원문을 반환합니다. L1이 `source_text_policy: on_demand`인 대형 문서는 inline CTX 텍스트가 아니라 원본 파일에서 필요한 구간을 읽습니다. `curator_query` 기반 검색은 L3 완료 후 사용합니다.
- **파라미터**: `source_key` (logical_source_id 또는 file_hash), `toc_id` (CTX frontmatter의 toc 배열 id), `page_start`/`page_end` (ToC 없는 PDF fallback).
- **구현 상태**: `source_key`가 등록 source 또는 파일 경로일 때 CTX section marker, 원문 heading, PDF page 단위 텍스트를 반환합니다. v0.2.1 기본 설정(`llm.instant_l1: true`)에서는 L1 CTX가 LLM 없이 생성되므로 섹션 조회가 빠르게 가능해집니다.
- **에이전트 활용 패턴**: 시스템 프롬프트에 주입된 ToC 미니맵을 보고 필요한 `toc_id`를 직접 호출.

#### `curator_query`

- **역할**: 자연어 질문으로 L3 Concept 지식 그래프를 검색하고, LLM이 답변을 합성하여 반환합니다. 동일한 질문+워크스페이스 조합의 Exhibition이 캐시되어 있으면 LLM 재호출 없이 즉시 반환합니다. L3가 아직 없는 소스에는 `search_curator`(raw 검색)로 자동 fallback됩니다.
- **파라미터**:
  - `question` (자연어 질문, 필수)
  - `workspace_path` (워크스페이스 절대 경로, 없으면 `WORKSPACE_PATH` 환경변수 또는 `"default"`)
  - `force_new` (캐시 무시하고 새 Exhibition 생성, 기본값 `false`)
- **반환값**: `ok`, `answer` (마크다운 답변), `exhibition_id` (생성·재사용된 EXH UUID), `cache_hit`, `question`, `trace`.
  - `trace`: `matched_concepts` (CON-ID 목록), `source_paths`, `latency_ms`, `l3_complete`.
- **컨텍스트 상한**: 합성 단계는 scope가 제한된 L3 Concept context를 사용하고, oversized source body는 LLM 호출 전에 잘라냅니다. 큰 L1 source recap이나 raw PDF text는 `curator_query`에 통째로 넣지 않고 source/PDF tool로 명시적으로 가져와야 합니다.
- **캐시 키**: `sha256(workspace_id + ":"+ normalized_question)[:16]`. backprop이 참조 CON을 수정하면 해당 캐시가 자동 무효화됩니다. `is_verified_by_human=true`인 EXH는 보호됩니다.
- **구현 상태**: v0.2.1에서 구현 완료. 워크스페이스 query도 ephemeral query-generated EXH를 저장하므로 같은 질문을 반복하면 LLM 재합성 없이 캐시에서 반환합니다. L3 미완성 소스의 경우 `ok=true`, `fallback="l3_incomplete"`, `answer=""`, `trace.l3_complete=false`를 반환하고 플러그인은 `fetch_document_section` 또는 로컬 PDF context fallback으로 전환합니다.

#### `promote_exhibition`

- **역할**: 에이전트가 생성한 Query-gen Exhibition을 사용자가 검토한 후 `02_Wiki/<category>/<slug>.md`로 영구 승격합니다. 승격된 EXH는 `exhibition_origin: promoted`, `is_verified_by_human: true`로 설정되어 backprop 재빌드에서 보호됩니다. **반드시 사용자의 명시적 승인 후에만 호출해야 합니다.**
- **파라미터**:
  - `exh_id` (EXH 노드 ID, 예: `"EXH-12345678"`)
  - `workspace_path` (워크스페이스 절대 경로, 선택)
- **반환값**: `ok`, `exhibition_id`, `promoted_to` (02_Wiki/ 상대 경로).
- **구현 상태**: v0.2.1에서 구현 완료. LLM이 카테고리/슬러그를 자동 분류하여 경로를 결정합니다.

#### `check_ingest_status`

- **역할**: 백그라운드 ingest job 큐의 현재 상태를 반환합니다. 플러그인이 `wiki add` 또는 `import_source` 이후 L2/L3 처리 완료를 감지하기 위해 5초 간격으로 폴링합니다. `idle: true`가 되면 폴링을 멈추고 UI를 갱신합니다.
- **파라미터**: `workspace_path` (절대 경로, 선택).
- **반환값**:
  - `ok` (항상 true)
  - `running` — 현재 실행 중인 job 목록 (`source_name`, `phase`, `progress`, `progress_current`, `progress_total` 포함)
  - `queued` — 대기 중인 job 목록
  - `done_today` — 오늘 완료된 job 수
  - `idle` — `running`과 `queued`가 모두 비어있으면 `true`
- **구현 상태**: v0.2.1에서 구현 완료. `.curator/dashboard.md`도 IngestWorker가 job 상태 변경마다 자동 갱신합니다(Obsidian live preview가 파일 변경 감지 후 자동 재렌더링).

#### `get_available_models`

- **역할**: 백엔드에 번들된 `models.json`에서 provider별 사용 가능 모델 목록을 반환합니다. 이 도구는 외부 MCP 클라이언트용입니다. Obsidian 플러그인은 빌드 시 같은 백엔드 `models.json`을 번들링하므로 모델 드롭다운 표시를 위해 이 MCP 도구가 필요하지 않습니다.
- **파라미터**: 없음.
- **반환값**: `{ "antigravity": [...], "claude": [...] }` 형태의 provider별 모델 목록.

> 참고: Obsidian plugin의 로컬 Zotero 및 dashboard 흐름은 MCP가 필요하지 않습니다.
> backend-owned runtime snapshot과 backend JSON command를 사용합니다.

#### `curator_get_version`

- **역할**: Incurator 백엔드의 현재 설치 버전을 문자열(예: `"0.2.2"`)로 반환합니다. 외부 클라이언트가 backend capability를 확인할 때 사용합니다.
- **파라미터**: 없음.
- **반환값**: 백엔드 버전 문자열.

### 3.5 워크스페이스 관리

#### `curator_workspace_init`

- **역할**: `curate.yml`, 에이전트 룰, Artist 페르소나를 자동 생성하며 새 워크스페이스를 초기화합니다. `curator_check_workspace`가 `curate.yml` 누락을 보고할 때, 또는 사용자가 워크스페이스를 Curator에 연결하려 할 때 호출합니다.
- **파라미터**: `workspace_path` (절대 경로), `project` (슬러그), `description`, `domains` (목록), `topics` (목록), `min_confidence`.
- **에이전트 자동 감지**: 연결된 클라이언트 런타임(Claude, Antigravity, Codex 등)을 자동 감지하여 해당 룰 파일을 설치합니다.
- **시나리오 처리**:
  - *빈 디렉토리* — 모든 파일을 새로 생성합니다.
  - *에이전트 룰만 있음* — LLM이 기존 룰 파일을 읽고 Curator hooks를 통합합니다. LLM 사용 불가 시 `integration_prompt`를 반환합니다.
  - *Curator 이미 연결됨* — 소유 파일을 최신 템플릿으로 갱신하고 managed block을 교체합니다.
- **반환값**: `ok`, `workspace`, `agent`, `scenario`, `created`, `updated`, `persona`, `rule_integration` (LLM 자동 수정 시), `integration_prompt` (LLM 불가 시), `recommended_next_steps`.

#### `curator_check_workspace`

- **역할**: 워크스페이스 상태를 검증하고 활성 Exhibition을 primary context로 로딩합니다. **도메인 쿼리에 응답하기 전 매 세션 시작 시 반드시 호출해야 합니다.**
- **파라미터**: `workspace_path` (워크스페이스 절대 경로).
- **반환값**: `ok`, `workspace`, `project`, `scenario`, `exhibition`, `exhibition_exists`, `issues`.
  - `scenario`가 `"agent-only"`이면 Curator 룰이 아직 미설치 상태입니다 — `curator_workspace_init`으로 해결하세요.

### 3.5 페르소나 관리

#### `curator_update_artist_persona`

- **역할**: 워크스페이스의 `curate.yml` 내 Artist `persona:` 블록을 자연어 요청으로 업데이트합니다.
- **파라미터**: `workspace_path` (워크스페이스 절대 경로), `request` (자연어 요청 문자열).
- **예시 요청**: `"이 워크스페이스는 컴퓨터 비전 연구자를 위한 공간입니다. 신뢰도 임계값을 0.85로 설정하고 exhibition_intent를 researcher로 지정해주세요."`

#### `curator_update_curator_persona`

- **역할**: `.curator/config.yml` 내 Curator `persona:` 블록을 자연어 요청으로 업데이트합니다.
- **파라미터**: `request` (자연어 요청 문자열).
- **예시 요청**: `"나는 STEM 분야의 연구자로, 주로 머신러닝과 시스템 설계를 다룹니다. 지식의 엄밀성을 중시하며 고신뢰도(0.85 이상) 정보만 활용합니다."`

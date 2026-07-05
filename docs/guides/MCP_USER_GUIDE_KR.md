# 🔌 MCP 사용법 가이드: 에이전트 연결하기


**Incurator MCP 서버**는 아티스트(인간 + 에이전트)가 큐레이터와 직접 상호작용하는 인터페이스입니다. Claude Desktop, Claude Code, Antigravity 등 워크스페이스 내의 에이전트는 이 MCP 서버를 통해 live DAG를 질의하고, 근거를 검사하며, 대화 중 발견한 오류나 새로운 인사이트를 지식 그래프에 반영할 수 있습니다. 이를 통해 아티스트의 피드백이 지식 그래프로 전파되어 사전 지식이 교정되는 순환 구조가 완성됩니다.

[English Guide](MCP_USER_GUIDE.md)

---

## 1. 사전 요구 사항

MCP 의존성 패키지가 설치되어 있는지 확인하세요.
```bash
uv pip install -e './backend[mcp]'
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
- **역할**: DB-native hybrid search로 저장소 전체를 검색합니다: FTS5 lexical
  retrieval, chunk-level vector, typed query expansion, RRF, configured reranking.
  Tier-2 LLM/HyDE expansion은 기본적으로 recovery-only이며 raw lexical/vector
  confidence가 낮을 때만 실행됩니다.
- **인덱싱**: 파생 markdown projection이 아니라 authoritative DB search row를
  검색합니다. 대기 중인 소스를 그래프에 반영하려면 검색 전에 `wiki add`/`wiki build`를 실행합니다.
- **파라미터**: `query`, `scope` (contexts/atoms/concepts/synthesis), `mode`, `limit`.

#### `curator_layer_index`
- **역할**: 각 레이어별 페이지 수와 최근 노드 샘플을 확인하여 저장소의 전반적인 상태를 파악합니다.

#### `curator_status`
- **역할**: 저장소 경로 및 검색 엔진 준비 상태를 확인합니다.

### 3.2 DAG 분석 및 순회

#### `curator_get_node`
- **역할**: 노드 ID(예: `SYN-abc12345`)를 통해 해당 마크다운의 전체 내용을 가져옵니다.

#### `curator_traverse_evidence`
- **역할**: Synthesis 노드를 기준으로 하위 Concept/Report/Atom/source span으로 이어지는 증거 체인을 조회하여 주장을 검증합니다.

#### `curator_find_contradictions`
- **역할**: 인간의 검토가 필요하거나 모순되는 주장이 포함된 Atom 목록을 조회합니다.

#### `curator_dismiss_contradiction`
- **역할**: 사용자나 에이전트가 무효하거나 중요하지 않다고 판단한 모순을 무시(Dismiss) 처리합니다.
- **파라미터**: `contradiction_id`, `reason`, `workspace_path` (선택).

#### `curator_resolve_contradiction`
- **역할**: 병합된 해결책이나 정정된 내용을 제공하여 모순을 해결합니다.
- **파라미터**: `contradiction_id`, `resolution_text`, `workspace_path` (선택).

#### `curator_get_provenance`
- **역할**: 생성된 특정 지식의 전체 출처 체인(원본 소스, Atom, Concept)을 검색합니다.
- **파라미터**: `node_id`, `workspace_path` (선택).

### 3.3 지식 관리 및 업데이트

#### `curator_import_source`
- **역할**: Zotero 등 외부 디렉토리의 파일을 Incurator backend에 등록합니다. 정책에 따라 파일을 복사하지 않는 Reference Mode로 연결하거나, 사용자가 승인한 `04_Resources/` 목적지로 안전하게 복사할 수 있습니다.
- **파라미터**: 구현 단계에 따라 `file_path` 또는 `source_path`가 입력 이름으로 사용될 수 있습니다. 둘 다 외부 파일의 절대 경로를 의미합니다. 정책 필드는 `policy="reference"` 또는 `destination_policy="mirror_03_to_04"`처럼 명시합니다. 실제 클라이언트는 먼저 `dry_run=true`로 제안 결과를 받은 뒤 사용자 승인 후 mutation을 호출해야 합니다.
- **목적지 규칙**: 외부 PDF의 기본값은 Reference Mode입니다. backend는 `04_Resources/` 아래에 markdown reference stub을 만들고 PDF 원본은 기존 위치에 둡니다. Copy mode는 명시적으로 선택할 때만 사용하며, 이 경우에도 목적지는 `03_Notes`가 아니라 `04_Resources`입니다.
- **portable identity**: Zotero import는 effective attachment key
  (`zotero:<key>`)만 저장하고 backend가 현재 기기의 Zotero DB에서
  해석합니다. 다른 external import는 등록된 named root가 필요하며
  `@<root_key>/<relative-path>`를 저장합니다. 해석된 절대경로는 durable
  state에 저장하지 않습니다.
- **덮어쓰기 금지**: 동일 해시 파일은 기존 source를 재사용하고, 같은 이름이지만 다른 해시인 파일은 suffix 또는 사용자 선택 목적지를 사용해야 합니다.

#### `curator_register_source`
- **역할**: 깊은 LLM 처리 없이 구조 기반으로 소스를 빠르게 등록(L1 생성)합니다.
- **파라미터**: `file_path` 또는 `source_path`.
- **반환**: 성공 시 `warnings`를 포함합니다. best-effort search index
  refresh가 index/database의 일시적 사용 불가 상태 때문에 건너뛰어지면,
  등록은 성공으로 유지되고 건너뛴 refresh가 이 필드에 보고됩니다.
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
- **v0.8.0**: 리포트에 Compiler Integrity 감사가 추가됩니다 —
  unsupported/failed/stale 클레임 수, evidence hash 불일치, broad-fallback
  발견 사항, formula status 불일치. 도구의 입력 스키마는 변경되지 않으며
  리포트 내용만 풍부해집니다. 에이전트는 릴리스를 막아야 하는 감사 발견
  사항을 끊어진 링크와 동일하게 취급해야 합니다: 수정하거나 에스컬레이션하고,
  절대 무시하지 않습니다. 또한 query/search 도구가 반환하는 증거는 이제
  200자 미리보기 대신 (소스와 해시 검증된) 전체 span 텍스트를 하이드레이션하며,
  클레임에는 `support_status`/`formula_status` 라벨이 포함됩니다 —
  `unchecked`, `failed`, `stale` 또는 retired 클레임을 검증된 지식으로
  제시해서는 안 됩니다.

#### `curator_ingest_source` (Deprecated)
- **역할**: 기존의 통합된 ingestion 도구입니다. 대신 `curator_register_source`와 `curator_build_source`를 사용하세요.

#### `curator_list_external_resources`
- **역할**: 기기별 로컬 설정(저장소 루트의 `.cache/config/config.yml`)에 정의된 외부 라이브러리(예: Zotero) 목록과 현재 활성화된 절대 경로를 반환합니다.



#### `curator_rebind_source`
- **역할**: 외부 참조 파일의 해시가 변동(Hash Drift)되거나 물리적 위치가 이동된 경우, 인간의 승인을 거쳐 새로운 경로와 해시로 식별자(`logical_source_id`)를 리바인딩(Healing)합니다.
- **파라미터**: `logical_source_id` (고유 식별자), `new_path` (새로운 절대 경로).
- **주의**: 이 도구는 반드시 Human-in-the-Loop 승인 뒤에 호출되어야 합니다. backend는 제안과 실행을 구분해야 하며, client는 어떤 파일이 어떤 logical source로 묶이는지 사용자에게 보여줘야 합니다.

#### `curator_search_sources`
- **역할**: 특정 source 또는 PDF 페이지 범위 안에서만 검색합니다. Obsidian 플러그인이 현재 열린 PDF 질문을 backend RAG 결과와 결합할 때 사용합니다.
- **파라미터**: `query`, `source_id` 또는 `source_path`, 선택적으로 `page_start`, `page_end`, `limit`, `mode`.
- **반환값**: page number, score, snippet, source provenance를 포함해야 합니다.
- **참고**: 이전의 단수형 alias `curator_search_source`는 v0.2.1에서 제거되었습니다.


#### `curator_get_pdf_context`

- **역할**: adaptive PDF chat context. 등록되고 L1 완료된 source는 원본 PDF를
  다시 파싱하지 않고 durable CTX projection을 제공합니다. 그 외에는 source를
  등록하지 않는 read-only on-demand 추출을 수행합니다. `<pdf_window>`,
  `<document_outline>` context block을 조립하는 기본 툴입니다.
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
  - `context_source`: `durable_l1_projection` 또는 `ephemeral_parse`.
  - `degraded_reason`: durable context가 exact text를 제공하지 못한 선택적 이유.
- **기존 문제 해결**: 이전에 플러그인은 `pdf_window`, `document_outline`, `pdf_rag_hits` 세 가지 MCP 호출을 했는데 모두 backend에 없어서 silent fail했음. 이 툴이 하나의 호출로 통합.
- **성능**: 등록된 L1 source는 CTX projection을 먼저 읽습니다. ephemeral/degraded
  fallback은 `parse_page_window()`로 필요한 페이지만 읽어 600페이지 PDF도 전체
  메모리 로드 없이 안전하게 처리합니다.

#### `curator_get_pdf_toc`
- **역할**: PDF에서 raw ToC를 직접 추출합니다. 등록된 L1 source는 원본 PDF를
  다시 파싱하지 않고 durable CTX ToC를 반환할 수 있는
  `curator_get_pdf_context`를 우선 사용합니다.
- **파라미터**: `file_path` (PDF 절대 경로).
- **반환값**: `[{title, page, level}]`

#### `curator_add_knowledge`
- **역할**: 대화 중 얻은 귀중한 통찰이나 정보를 **Wiki(02_Wiki/)** 페이지로 승격하여 영구 저장합니다. 카테고리 분류와 슬러그 생성이 자동으로 수행됩니다.

#### `curator_update_node`
- **역할**: 상태를 변경하지 않는 비활성 endpoint입니다. 생성 노드를 직접 덮어쓰는 방식은 지원하지 않습니다.
- **대신 사용**: 검토된 정정은 `curator_propose_correction`, 지속 지식 승격은 `promote_answer` / `curator_promote_insight`를 사용합니다.

#### `curator_propose_correction`
- **역할**: 권위 생성 레코드를 대상으로 정정을 제안합니다. 백엔드는 제안을
  분류하고 권장 동작을 반환하지만 대상을 자동으로 덮어쓰지 않습니다.
  `.curator/Collections/`의 Markdown 페이지는 파생된 검사 projection이므로 이를
  편집하는 것은 정정 메커니즘이 아닙니다.
- **파라미터**: `node_id`, `correction`, `workspace_path`(선택),
  `previous`(선택적 이전 artifact 텍스트).
- **백엔드 처리**: classification, recommended action, affected node id,
  review requirement, trace id, provisional insight candidate를 반환합니다.

#### `curator_reindex`
- **역할**: DB-native search state(`search_documents`, `search_chunks`, FTS5 row,
  missing/stale chunk embedding)를 수동으로 다시 빌드합니다.
- **Degraded result**: lexical FTS5는 최신이지만 embedding, query expansion,
  reranking 중 일부를 사용할 수 없으면 `ok=true`, `degraded=true`를 반환합니다.
  Query trace에는 `vector_unavailable`, `query_expander_unavailable`,
  `reranker_unavailable` 같은 경고가 기록됩니다.

### 3.4 문서 상태 및 On-demand 쿼리 (v0.2.1)

#### `check_source_status`

- **역할**: 파일의 SHA-256 해시로 Incurator 등록 상태를 조회합니다. 플러그인은
  backend PDF context 또는 명시적 Add/status 동작이 ephemeral mode, durable L1
  section serving, L3-complete `curator_query`를 구분해야 할 때 호출합니다. local
  viewer context는 이 호출을 기다리지 않습니다.
- **파라미터**: `file_hash` (파일 SHA-256 해시 문자열).
- **반환값**: `registered`, `source_id`, `l1_complete`, `l2_complete`, `l3_complete`, `jobs_pending`.
- **구현 상태**: 백엔드는 `sources.content_hash`를 조회하고 queued/running `ingest_jobs`를 함께 반환합니다.
- **참고**: 경로가 달라도(터미널 절대경로 vs 플러그인 상대경로) 동일 해시면 같은 결과를 반환합니다. `wiki add` CLI 경로와 플러그인 경로가 투명하게 통합됩니다.

#### `fetch_document_section`

- **역할**: 등록된 문서의 특정 섹션 텍스트를 CTX section id, 원본 heading,
  또는 PDF page range로 반환합니다. 미등록 viewer turn은 이 도구를 호출하지 않고,
  플러그인의 local in-memory PDF.js context 또는 read-only backend PDF-context
  fallback을 사용합니다. L1이 `source_text_policy: on_demand`인 대형 문서는 inline
  CTX 텍스트가 아니라 원본 파일에서 필요한 구간을 읽습니다. `curator_query`는 L3
  완료 후 사용합니다.
- **파라미터**: `source_key` (logical_source_id 또는 파일 경로), `content_hash` (소스 파일 SHA-256 hex — vault 경로를 모를 때 대체 조회 키, 플러그인의 `fileHash` 필드에서 제공), `toc_id` (CTX frontmatter의 toc 배열 id), `page_start`/`page_end` (ToC 없는 PDF fallback).
- **페이지 캐시 (v0.26.0)**: `content_hash`와 함께 PDF 페이지 범위 요청(`page` / `page_start` / `page_end`)이 들어오면, `.cache/pdf_pages/<hash>/<pagenum>.txt` 경로의 영구 캐시를 활용합니다. 캐시 히트 시 PDF 재파싱 없이 즉시 반환하고, 미스 시 요청된 페이지만 선택적으로 파싱한 뒤 결과를 캐시에 저장합니다. 응답에는 `context_source` (`pdf_page_cache` / `pdf_page_cache_partial`), `cache_hits`, `cache_misses` 필드가 포함됩니다.
- **구현 상태**: `source_key` 또는 `content_hash`가 등록 source 또는 파일 경로로 해석될 때 CTX section marker, 원문 heading, PDF page 단위 텍스트를 반환합니다. v0.2.1 기본 설정(`llm.instant_l1: true`)에서는 L1 CTX가 LLM 없이 생성되므로 섹션 조회가 빠르게 가능해집니다.
- **에이전트 활용 패턴**: 시스템 프롬프트에 주입된 ToC 미니맵을 보고 필요한 `toc_id`를 직접 호출. 팝오버의 수식 교차 페이지 조회 시, 뷰어에 PDF가 열려 있지 않으면 플러그인이 `content_hash` + `page`로 이 도구를 호출합니다.

#### `curator_query`

- **역할**: 자연어 질문에 대해 동적 Curation 렌즈(DB 그래프 + source span,
  atom, report, 공유 L4 Synthesis 레이어에 대한 DB-native hybrid search)로 답변을
  합성하여 반환합니다. **세션리스**: 답변 + 트레이스를 반환하며 어떤 vault 파일도 쓰지 않습니다.
- **파라미터**:
  - `question` (자연어 질문, 필수)
  - `workspace_path` (워크스페이스 절대 경로, 없으면 `WORKSPACE_PATH` 환경변수 또는 `"default"`)
- **반환값**: `ok`, `answer` (마크다운 답변), `question`, `trace`.
  - `trace`: `matched_concepts` (CON-ID 목록), `source_paths`, `synthesis_node_ids`, `community_report_ids`, `source_span_ids`, `prompt_trace_ids`, `trace_id`(`QTR-`), `route`, `pack_id`, `snapshot`, `budget`, `latency_ms`, `l3_complete`. 합성 답변의 `source_span_ids`는 전체 검색 pack이 아니라 검증된 답변 출력이 실제 인용했다고 보고한 span입니다. `pack_id`, `snapshot`, `budget`은 ContextService-backed route에서만 값이 채워지며, 아직 ContextService로 이전되지 않은 route는 이 필드를 `null`로 반환합니다.
- **컨텍스트 상한**: ContextService가 합성 전에 context budget을 적용하고, synthesizer는 이미 budget 처리된 pack 전체를 받습니다. 큰 L1 source recap이나 raw PDF text는 `curator_query`에 통째로 넣지 않고 source/PDF tool로 명시적으로 가져와야 합니다.
- **구현 상태**: v0.3.2. L3 미완성 소스의 경우 degraded trace를 남기고 가능한
  DB-native lexical/vector retrieval을 사용합니다. 합성 없는 증거 팩이 필요하면
  `curator_fetch_context`를 사용하세요.

#### `promote_answer`

- **역할**: 세션리스 Q&A 답변을 사용자가 검토한 후 `02_Wiki/`로 승격합니다. `02_Wiki/`에만 쓰며 소스 진실은 절대 건드리지 않습니다. **반드시 사용자의 명시적 승인 후에만 호출해야 합니다.**
- **파라미터**:
  - `question`, `answer` (승격할 텍스트)
  - `workspace_path` (선택)
  - `source_span_ids` (선택 — 답변 쿼리 trace의 `source_span_ids`)
- **반환값**: `ok`, `promoted_to` (02_Wiki/ 상대 경로).
- **소스 문서**: `source_span_ids`가 전달되면 승격된 페이지에 `## Sources` 섹션이
  결정적으로(deterministic) 추가되어, 답변의 근거가 된 모든 원본 소스 문서를
  `[[04_Resources/…]]` 링크로 나열합니다(여러 소스를 합성한 경우 첫 번째뿐 아니라
  기여한 모든 소스 포함). `02_Wiki/` 노트는 숨김이 아닌 일반 vault 파일이므로 이
  소스들이 Obsidian의 그래프 뷰·백링크 패널에 나타납니다 — 숨겨진 DAG는 불가능.
  이 기능을 켜려면 trace의 `source_span_ids`를 넘기세요.
- **구현 상태**: v0.3.1. LLM이 카테고리/슬러그를 자동 분류합니다. (검토된 인사이트 후보를 승격하려면 `curator_promote_insight`를 사용하세요.)

#### `check_ingest_status`

- **역할**: 백그라운드 ingest job 큐의 현재 상태를 반환합니다. 플러그인은 명시적
  Add Source 등록이 L2/L3 작업을 queue에 넣은 뒤 이 상태를 폴링합니다.
  `idle: true`가 되면 폴링을 멈추고 UI를 갱신합니다.
- **파라미터**: `workspace_path` (절대 경로, 선택).
- **반환값**:
  - `ok` (항상 true)
  - `running` — 현재 실행 중인 job 목록 (`source_name`, `phase`, `progress`, `progress_current`, `progress_total` 포함)
  - `queued` — 대기 중인 job 목록
  - `done_today` — 오늘 완료된 job 수
  - `idle` — `running`과 `queued`가 모두 비어있으면 `true`
- **구현 상태**: v0.2.1에서 구현 완료. backend-local dashboard cache도 IngestWorker가 job 상태 변경마다 자동 갱신합니다.

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
- **에이전트 자동 감지**: 연결된 클라이언트 런타임(Claude, Antigravity, Codex 등)을 자동 감지하여 해당 룰 파일만 설치합니다. Codex와 Antigravity는 `AGENTS.md`를 공유하므로, 그 파일의 managed Curator block은 감지된 런타임 기준으로 렌더링됩니다. vault root는 서버를 시작할 때 지정한 `VAULT_ROOT` 환경변수에서 결정되며(우선), `curate.yml.vault_root`는 — 동기화된 여러 기기에서 이식 가능하도록 워크스페이스 디렉토리 기준 상대 경로로 작성됩니다 — standalone 도구 호출 시에만 쓰이는 fallback입니다.
- **시나리오 처리**:
  - *빈 디렉토리* — 모든 파일을 새로 생성합니다.
  - *에이전트 룰만 있음* — LLM이 기존 룰 파일을 읽고 Curator hooks를 통합합니다. LLM 사용 불가 시 `integration_prompt`를 반환합니다.
  - *Curator 이미 연결됨* — 소유 파일을 최신 템플릿으로 갱신하고 managed block을 교체합니다.
- **반환값**: `ok`, `workspace`, `agent`, `scenario`, `created`, `updated`, `persona`, `rule_integration` (LLM 자동 수정 시), `integration_prompt` (LLM 불가 시), `recommended_next_steps`.

#### `curator_check_workspace`

- **역할**: 워크스페이스 상태를 검증하고 `curate.yml` 룰을 로딩합니다. **도메인 쿼리에 응답하기 전 매 세션 시작 시 반드시 호출해야 합니다.**
- **파라미터**: `workspace_path` (워크스페이스 절대 경로).
- **반환값**: `ok`, `workspace`, `project`, `scenario`, `issues`.
  - `scenario`가 `"agent-only"`이면 Curator 룰이 아직 미설치 상태입니다 — `curator_workspace_init`으로 해결하세요.

### 3.5 페르소나 관리

#### `curator_update_artist_persona`

- **역할**: 워크스페이스의 `curate.yml` 내 Artist `persona:` 블록을 자연어 요청으로 업데이트합니다.
- **파라미터**: `workspace_path` (워크스페이스 절대 경로), `request` (자연어 요청 문자열).
- **예시 요청**: `"이 워크스페이스는 컴퓨터 비전 연구자를 위한 공간입니다. 신뢰도 임계값을 0.85로 설정하고 출력 스타일을 연구 가설 중심으로 맞춰주세요."`

#### `curator_update_curator_persona`

- **역할**: `.curator/settings.yml` 내 Curator `persona:` 블록을 자연어 요청으로 업데이트합니다.
- **파라미터**: `request` (자연어 요청 문자열).
- **예시 요청**: `"나는 STEM 분야의 연구자로, 주로 머신러닝과 시스템 설계를 다룹니다. 지식의 엄밀성을 중시하며 고신뢰도(0.85 이상) 정보만 활용합니다."`

### 3.6 큐레이션-네이티브 도구 (v0.3.3)

v0.3.2 큐레이션-네이티브 컴파일러를 노출하는 도구들입니다: `curate.yml` 정책 컴파일,
쿼리 오케스트레이터의 explore 라우트, 프롬프트 실행 트레이스, 파생-인사이트
라이프사이클. CLI·플러그인과 동일한 공유 서비스를 사용하며, 읽기 전용 원본
(`03_Notes/`, `04_Resources/`, `06_Archives/`)은 절대 수정하지 않습니다.

#### `curator_validate_curate_spec`

- **역할**: 워크스페이스 `curate.yml`(지식 요구 명세, KRS)을 검증하고 컴파일된 런타임 정책 요약을 반환합니다.
- **파라미터**: `workspace_path`.
- **반환**: `ok`, `errors`, `spec_hash`, `policy`(`default_route`, `allowed_routes`, `prompt_profile`, `require_source_spans`, `backprop_enabled`).

#### `curator_plan_workspace`

- **역할**: `curate.yml`을 `curation_plans` 레코드(명세와 큐레이션 실행을 잇는 검사 가능한 다리)로 컴파일·기록합니다.
- **파라미터**: `workspace_path`.
- **반환**: `plan_id`(`PLAN-…`), `workspace_id`, `route`.

#### `curator_fetch_context`

- **역할**: **큐레이션된 증거 팩**을 반환합니다 — 에이전트 자신의 추론 LLM이 근거로 삼아야 할, 워크스페이스 KRS로 편향된 증거 선택을 **합성된 답변 없이** 제공합니다. 이는 고정 파일이 아니라 *라이브 DAG 위의 동적 렌즈*로서의 큐레이션이며, 자체 합성을 수행하는 추론 에이전트(예: Obsidian 에이전트)의 1차 surface입니다. 광범위한 질문의 경우 팩은 공유 **L4 Synthesis** 노드를 앞세웁니다.
- **파라미터**: `query`, `workspace_path`(선택).
- **반환**: `route`, `trace_id`(`QTR-…`), `retrieval_execution_id`(`RTR-…`), `workspace_id`, `evidence`(각 항목은 `kind` — `synthesis` | `community_report` | `entity` | `source_span` | `memory_path` | `search_hit` — 와 `id`/`title`/`text`/`score`, 출처 id, 그리고 span 기반 항목의 경우 `source_kind`/`relpath`/`heading`/`locator_status`를 포함하는 `locator` 딕셔너리 포함), `source_span_ids`, `community_report_ids`, `synthesis_node_ids`, `memory_path_ids`, `warnings`. 검색 hit 근거는 hydrate된 `source_span_ids`를 보존하며, `trace_id`는 하나의 authoritative orchestrated query trace를 식별하고, `retrieval_execution_id`는 Plan F가 소비하는 자식 RTR-* ID입니다. 의도적으로 `answer` 필드는 **없습니다**.

Plan F에서는 이 surface가 통합 ContextService의 `context_fetch` 계약으로
업그레이드됩니다. 반환 pack은 versioned, budget-bounded, snapshot-stamped
형태이며 omission을 명시합니다. 확장과 정확 검증은 pack의 stable handle을
사용하고, snapshot이 바뀌면 backend는 오래된 근거와 새 근거를 섞지 않고
typed conflict를 반환합니다. 확장된 handle은 같은 pack snapshot 안에서 한 번만
소비됩니다. 요청 budget으로 handle을 담을 수 없으면 backend는 그 handle을
`next`에 다시 넣지 않고 `expansion_refused`에 표시하므로 agent가 같은 불가능한
확장을 반복하지 않습니다.

#### `curator_explore`

- **역할**: 쿼리 오케스트레이터의 **explore** 라우트 실행. 비자명한 연결을 발견하고 HippoRAG식 메모리 경로를 기록하며 잠정 인사이트 후보를 생성합니다. 공유 L4 synthesis 노드 + 커뮤니티 리포트로 primer를 구성하고, DB 그래프와 authoritative record에 대한 DB-native hybrid search를 결합합니다.
- **통합 팩 경로(v0.20.0)**: 이제 explore는 다른 라우트와 동일한 `ContextService` 팩 위에서 grounding합니다 — `PACK-*`/`SNAP-*` 스냅샷을 생성하고 공유 토큰 예산을 따르며, 후속 질문/인사이트 생성은 별도의 검색 파이프라인이 아니라 그 정규화된 팩을 소비하는 synthesis 단계로 수행됩니다(SYSTEM_BEHAVIOR §31.8). `curator_fetch_context`도 이제 discovery 신호 질문을 `local`로 강등하지 않고 explore 라우트 grounding을 반환합니다.
- **파라미터**: `query`, `workspace_path`(선택).
- **반환**: `answer`, `route`, `trace_id`(`QTR-…`), `synthesis_node_ids`, `memory_path_ids`, `insight_candidate_ids`, `prompt_trace_ids`, `warnings`.

#### `curator_get_prompt_trace`

- **역할**: 기록된 프롬프트 실행(`PTR-…`) 하나를 반환 — 프롬프트 id/버전, 모델, 검증자 상태/오류, 입출력 해시.
- **파라미터**: `trace_id`, `workspace_path`(선택).

#### `curator_list_insight_candidates`

- **역할**: 잠정 인사이트 후보(파생 인사이트, 정정, 검토 대기 모순)를 나열합니다. 후보는 **사람이 검증한 진실이 아닙니다.**
- **파라미터**: `workspace_path`(선택), `status`(기본 `pending`).

#### `curator_promote_insight`

- **역할**: 명시적 승인 후 인사이트 후보를 `02_Wiki/`의 영구 노트로 승격합니다. `02_Wiki/`에만 기록하고 후보를 `promoted`로 설정합니다.
- **파라미터**: `insight_id`, `workspace_path`(선택).

#### `curator_propose_correction`

- **역할**: 생성된 노드에 정정을 제안합니다. 변경은 **패치 전에 먼저 분류**됩니다(correction / contradiction / derived_insight / style_only / promotion_request / ambiguous). 원본 진실은 절대 재작성되지 않으며, 파생 인사이트는 잠정 후보가 되고 정정은 생성된 노드만 대상으로 합니다.
- **파라미터**: `node_id`, `correction`, `workspace_path`(선택), `previous`(선택, 이전 산출물 텍스트).
- **반환**: `classification`, `recommended_action`, `patch_node_ids`, `requires_human_review`, `insight_candidate_id`, `trace_id`, `reason`.

### 3.7 Zotero 연동 (Zotero Integration)

#### `curator_search_zotero_items`
- **역할**: 제목이나 저자로 Zotero 항목을 검색합니다.
- **파라미터**: `query`, `workspace_path` (선택), `custom_paths` (선택), `limit`.

#### `curator_get_zotero_item_metadata`
- **역할**: 특정 Zotero 항목의 상세 메타데이터를 가져옵니다.
- **파라미터**: `item_key`, `workspace_path` (선택), `custom_paths` (선택).

#### `curator_get_zotero_annotations`
- **역할**: Zotero PDF 첨부 파일에서 주석과 하이라이트를 추출합니다.
- **파라미터**: `item_key`, `workspace_path` (선택), `custom_paths` (선택).

#### `curator_resolve_zotero_pdf`
- **역할**: Zotero 항목에 대한 물리적 PDF 파일 경로를 찾습니다.
- **파라미터**: `item_key`, `workspace_path` (선택), `custom_paths` (선택).

### 3.8 환경 설정 관리 (Configuration Management)

#### `curator_get_provider_config`
- **역할**: 현재 구성된 LLM 공급자 설정을 가져옵니다.
- **파라미터**: `workspace_path` (선택).

#### `curator_set_provider_config`
- **역할**: LLM 공급자 설정을 동적으로 업데이트합니다.
- **파라미터**: `provider` (예: 'claude', 'antigravity'), `model`, `api_key` (선택), `workspace_path` (선택).

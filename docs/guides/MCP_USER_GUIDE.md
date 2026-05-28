# 🔌 MCP 사용법 가이드: 에이전트 연결하기


**Incurator MCP 서버**는 아티스트(인간 + 에이전트)가 큐레이터와 직접 상호작용하는 인터페이스입니다. Claude Desktop, Claude Code, Gemini CLI 등 워크스페이스 내의 에이전트는 이 MCP 서버를 통해 큐레이터가 준비한 전시물(Exhibition)을 탐색하고, 대화 중 발견한 오류나 새로운 인사이트를 사전 지식에 즉시 반영할 수 있습니다. 이를 통해 아티스트의 피드백이 지식 그래프로 전파되어 사전 지식이 교정되는 순환 구조가 완성됩니다.

[English Guide](MCP_USER_GUIDE_EN.md)

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
특정 클라이언트를 지정할 수도 있습니다: `wiki mcp install claude` 또는 `wiki mcp install gemini`.

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
- **목적지 규칙**: 외부 PDF의 기본 복사 목적지는 `03_Notes`가 아니라 `04_Resources`입니다. 활성 노트가 `03_Notes/Vision/Foo.md`라면 기본 제안은 `04_Resources/Vision/Foo/<pdf-file>.pdf`입니다. 연결된 노트가 없으면 `04_Resources/Inbox/<pdf-file>.pdf`를 제안합니다.
- **덮어쓰기 금지**: 동일 해시 파일은 기존 source를 재사용하고, 같은 이름이지만 다른 해시인 파일은 suffix 또는 사용자 선택 목적지를 사용해야 합니다.

#### `curator_list_external_resources`
- **역할**: 플랫폼별 글로벌 설정(`~/.config/curator/config.yml`)에 정의된 외부 라이브러리(예: Zotero) 목록과 현재 활성화된 절대 경로를 반환합니다.

#### `curator_source_status`
- **역할**: 파일의 처리 상태 및 외부 경로(`external_path`) fallback 로직 상태를 조회합니다. 위치가 이동되어 `MOVED` 상태인 파일들을 식별할 수 있습니다.
- **파라미터**: `source_id`, `logical_source_id`, `source_path`, 또는 `file_path` 중 구현이 지원하는 식별자를 사용합니다.
- **Obsidian 플러그인 표시**: 플러그인은 이 결과를 PDF chip의 상태 badge로 표시할 수 있습니다. 예: `untracked`, `queued`, `running L1`, `running L2`, `running L3`, `running L4`, `indexed`, `stale`, `moved`, `error`.

#### `curator_rebind_source`
- **역할**: 외부 참조 파일의 해시가 변동(Hash Drift)되거나 물리적 위치가 이동된 경우, 인간의 승인을 거쳐 새로운 경로와 해시로 식별자(`logical_source_id`)를 리바인딩(Healing)합니다.
- **파라미터**: `logical_source_id` (고유 식별자), `new_path` (새로운 절대 경로).
- **주의**: 이 도구는 반드시 Human-in-the-Loop 승인 뒤에 호출되어야 합니다. backend는 제안과 실행을 구분해야 하며, client는 어떤 파일이 어떤 logical source로 묶이는지 사용자에게 보여줘야 합니다.

#### `curator_search_source`
- **역할**: 특정 source 또는 PDF 페이지 범위 안에서만 검색합니다. Obsidian 플러그인이 현재 열린 PDF 질문을 backend RAG 결과와 결합할 때 사용합니다.
- **파라미터**: `query`, `source_id` 또는 `source_path`, 선택적으로 `page_start`, `page_end`, `limit`, `mode`.
- **반환값**: page number, score, snippet, source provenance를 포함해야 합니다.

#### `curator_get_pdf_page`
- **역할**: backend가 저장한 특정 PDF page text/provenance를 반환합니다.
- **파라미터**: `source_id` 또는 `source_path`, `page`.
- **용도**: plugin viewer context가 일시적으로 부족하거나 provider가 이미지 첨부를 무시하는 경우에도 텍스트 기반 컨텍스트를 안정적으로 보강합니다.

#### `curator_add_knowledge`
- **역할**: 대화 중 얻은 귀중한 통찰이나 정보를 **Wiki(02_Wiki/)** 페이지로 승격하여 영구 저장합니다. 카테고리 분류와 슬러그 생성이 자동으로 수행됩니다.

#### `curator_update_node`
- **역할**: 특정 노드(주로 Exhibition)의 내용을 업데이트합니다.
- **스마트 백프로파게이션 (Smart Backprop)**: **Exhibition (EXH)** 노드를 수정할 경우, 시스템이 시만틱 검색을 통해 관련 Concept(L3), Atom(L2)을 찾아 병합/수정하고, 나아가 **소스(L1 Context)**까지 변경 사항을 전파합니다. 출처가 불분명한 경우 사용자에게 피드백을 요청합니다.

#### `curator_reindex`
- **역할**: QMD 검색 인덱스를 수동으로 다시 빌드합니다.

### 3.4 워크스페이스 관리

#### `curator_workspace_init`

- **역할**: `curate.yml`, 에이전트 룰, Artist 페르소나를 자동 생성하며 새 워크스페이스를 초기화합니다. `curator_check_workspace`가 `curate.yml` 누락을 보고할 때, 또는 사용자가 워크스페이스를 Curator에 연결하려 할 때 호출합니다.
- **파라미터**: `workspace_path` (절대 경로), `project` (슬러그), `description`, `domains` (목록), `topics` (목록), `min_confidence`.
- **에이전트 자동 감지**: 연결된 클라이언트 런타임(Claude, Gemini, Codex 등)을 자동 감지하여 해당 룰 파일을 설치합니다.
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

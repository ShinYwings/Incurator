# Incurator 에이전트 워크플로우 가이드

이 문서는 Incurator MCP (Model Context Protocol) 서버의 공식 운영 시나리오와 도구 상호작용 패턴을 정의합니다. 높은 수준의 4단계 파이프라인 이론과 에이전트 또는 사용자의 명령에 의해 트리거되는 실제 실행 흐름을 연결합니다.

[English Guide](AGENT_WORKFLOW_GUIDE.md)

## 1. 환경 및 초기화 시나리오

### 1.1 세션 진입 및 동기화 (`curator_check_workspace`)
*   **트리거**: 모든 세션 시작 시 에이전트에 의해 자동으로 호출됩니다.
*   **논리 흐름**:
    1.  **경로 해석**: `workspace_path`에서 위로 이동하며 `vault_root`를 발견합니다.
    2.  **상태 검증**: `curate.yml`의 존재 여부와 검색 인덱스에 구성된 Exhibition이 있는지 확인합니다.
    3.  **결과**: 초기화 필요 여부(`needs_initialization`)와 Exhibition 존재 여부(`exhibition_exists`)를 반환합니다.

### 1.2 워크스페이스 스캐폴딩 (`curator_workspace_init`)
*   **트리거**: `check_workspace`가 `needs_initialization: true`를 반환할 때 시작됩니다.
*   **논리 흐름**:
    1.  **요구사항 명세**: 경로 이탈을 방지하기 위해 명시적인 `vault_root`를 포함한 `curate.yml`을 생성합니다.
    2.  **페르소나 설정**: LLM 인터뷰를 실행하여 Artist 페르소나(도메인, 목표, 의도)를 정의합니다.
    3.  **초기 빌드**: 즉시 `wiki build`를 트리거하여 공유 DAG(L2 Atom → L3 Concept → L4 Synthesis)를 정제해 에이전트가 근거로 삼을 증거를 확보합니다. 큐레이션 자체는 쿼리 시점의 동적 렌즈이며, 워크스페이스별 Exhibition은 생성되지 않습니다.

---

## 2. 질의 및 지식 검색 시나리오

### 2.1 페르소나 기반 질의 및 검색 (`curator_query` & `search_curator`)
*   **논리 흐름 (`curator_query`)**:
    1.  **이원화된 아키텍처(Dual Architecture) 적용**: 워크스페이스가 지정되면 `curate.yml`의 Pinned L4 Exhibition과 페르소나를 사용합니다(임시 파일 생성 안 함). 워크스페이스가 없는 일반 Vault 모드인 경우, 세션별로 임시(Ephemeral) L4 Exhibition을 동적으로 생성합니다.
    2.  **L3 제약 조건**: 질의와 관련된 L3 Concept이 존재할 때만 L4 Exhibition을 생성합니다. 없으면 L4 생성을 건너뛰고 직접 답변하거나 일반 검색으로 폴백합니다.
*   **논리 흐름 (`search_curator`)**:
    1.  로컬 `curate.yml`에서 `domains`, `topics`, `min_confidence` 필터를 자동으로 적용합니다.
    2.  대상 Exhibition이 없으면 검색을 수행하기 전에 **큐레이션 패스를 자동으로 트리거**합니다.
    3.  프로젝트의 지식 요구사항으로 범위가 지정된 결과를 반환하여 Vault의 관련 없는 부분에서 발생하는 "지식 노이즈"를 방지합니다.

### 2.2 근거 추적 (`curator_traverse_evidence`)
*   **상황**: 검색 결과 신뢰도 점수가 높은 임계값(0.90)보다 낮지만 낮은 하한선(0.60)보다는 높은 경우.
*   **논리 흐름**:
    1.  에이전트가 증거 체인을 거슬러 올라갑니다: `EXH → CON → ATM`.
    2.  작업 결과물에 정보를 인용하기 전에 특정 주장과 출처를 검증합니다.

### 2.3 외부 리소스 통합 및 해시 복구
*   **상황**: 파일을 Vault에 복사하지 않고 Zotero PDF와 같은 외부 참조를 연결하거나, Vault 외부에서 파일이 수정되었을 때 끊어진 링크를 복구하는 경우.
*   **논리 흐름**:
    1.  **설정**: 에이전트가 `curator_list_external_resources`를 호출하여 플랫폼 인식 설정에서 구성된 외부 라이브러리(예: Zotero 경로)를 가져옵니다.
    2.  **임포트 제안**: 상태 변경 전에 에이전트 또는 Obsidian 플러그인이 `curator_import_source(..., dry_run=true)`를 호출합니다. 백엔드는 계산된 해시, 감지된 중복 상태, 제안된 대상 또는 프록시 앵커, 해당 작업이 복사 모드인지 레퍼런스 모드인지 반환합니다.
    3.  **사용자 승인**: 클라이언트는 대상/정책을 사용자에게 제시합니다. 가시적인 승인 없이 외부 PDF를 `04_Resources/`에 복사하거나 레퍼런스로 등록해서는 안 됩니다.
    4.  **임포트**: 에이전트가 상태 변경을 활성화하여 `curator_import_source(policy="reference")` 또는 `curator_import_source(destination_policy="mirror_03_to_04")`를 호출합니다. 엔진은 파일의 콘텐츠 해시를 계산하고 소스 레코드를 생성하며, DB에 `is_reference`, `external_path`, `logical_source_id`, `import_origin`, `import_policy`를 기록합니다.
    5.  **상태 확인**: `curator_source_status`를 통해 외부 리소스의 상태를 가져올 때, 엔진은 `external_path` 캐시를 사용합니다.
    6.  **감지**: 파일이 수정되어(예: Apple Pencil 주석) "해시 드리프트(Hash Drift)"가 발생하거나 파일이 이동된 경우 다음 스캔 중에 `external_path` 캐시가 실패합니다. 엔진은 고속 `rglob` 재발견을 실행하고 소스 상태를 동적으로 `moved`나 `hash_drift`로 보고합니다.
    7.  **복구 (HITL)**: UI를 통해 사용자에게 알림이 표시됩니다 ("위치가 이동되었습니다. 다시 바인딩을 수락하시겠습니까?"). 사용자 승인 후, 에이전트는 `curator_rebind_source(logical_source_id, new_path)`를 호출하여 안전하게 연결을 재설정하고 DB를 업데이트하여 프록시 노트를 복구합니다.

### 2.4 소스 인식 PDF 검색
*   **상황**: 사용자가 Obsidian에서 PDF를 읽고 있으며 현재 페이지, 인접 페이지 및 이전에 수집된 소스 지식에 의존하는 질문을 합니다.
*   **논리 흐름**:
    1.  Obsidian 플러그인이 즉각적인 뷰어 컨텍스트(현재 페이지 텍스트, 활성화된 경우 현재 페이지 이미지, 인접 페이지 텍스트 창, 사용 가능한 경우 문서 목차 및 PDF 로컬 어휘 RAG 히트)를 캡처합니다.
    2.  플러그인이 `curator_source_status`를 호출하여 PDF가 미추적 상태인지, 대기 중인지, 실행 중인지, 인덱싱되었는지, 오래되었는지, 이동되었는지, 오류 상태인지 확인합니다.
    3.  소스가 인덱싱된 경우, 플러그인은 `curator_search_sources(query, source_id/source_path, limit=N)`를 호출하여 페이지 출처가 포함된 백엔드 RAG 히트를 검색할 수 있습니다.
    4.  최종 제공자 프롬프트에는 플러그인의 즉각적인 뷰어 컨텍스트와 백엔드 히트가 별도의 섹션으로 포함됩니다. 백엔드 히트가 뷰어 컨텍스트를 덮어써서는 안 됩니다. 뷰어 컨텍스트는 즉시성을 제공하는 반면 백엔드는 영구적인 출처를 제공합니다.

### 2.5 MCP 상태 변경 규칙
*   **조용한 노트 편집 금지**: MCP 도구는 `03_Notes/`를 편집해서는 안 됩니다.
*   **직접적인 플러그인 상태 쓰기 금지**: 플러그인은 `.curator/state.sqlite`를 수정해서는 안 됩니다.
*   **명시적인 Vault 루트**: `VAULT_ROOT` 또는 명시적인 `workspace_path`/`vault_root` 인수는 반드시 유효한 Vault로 해석되어야 합니다. 해석에 실패할 경우, MCP는 CWD로 폴백하지 않고 오류를 반환해야 합니다.
*   **덮어쓰기 임포트 금지**: 소스 임포트가 `04_Resources/`에 있는 기존 파일을 덮어써서는 안 됩니다. 동일한 해시의 중복은 기존 레코드를 재사용하며, 해시가 다른 파일명 충돌은 접미사 또는 사용자가 선택한 대상을 필요로 합니다.
*   **파괴적인 모호성을 위한 사전 Dry-run**: rebind나 임포트 충돌 복구와 같이 영구적인 소스 정체성을 변경하는 모든 작업은 실제 상태 변경 전에 dry-run/제안 결과를 지원해야 합니다.

---

## 3. 지식 진화 및 무결성 시나리오

### 3.1 역전파 (지식 교정)
*   **상황**: 사람(Director) 또는 에이전트(Artist)가 미리 컴파일된 Exhibition 또는 Concept에서 오류를 식별합니다.
*   **논리 흐름**:
    1.  에이전트가 `curator_update_node`를 통해 L4 Exhibition을 업데이트합니다.
    2.  엔진이 편집 내용을 구성 Concept과 Atom으로 거슬러 올라가며 **역방향 패스(Backward Pass)**를 트리거합니다.
    3.  엔진이 수정된 진실과 일치하도록 기본 DAG 노드에 수정을 제안하거나 적용합니다.
    4.  `wiki sync`를 통해 수정 사항이 네트워크 전체에 전파되도록 합니다.

### 3.2 통합 승격 (무한 루프 - Path B)
*   **상황**: 대화 세션 중에 가치 있는 통찰이 도출됩니다.
*   **논리 흐름**:
    1.  사용자가 `curator_add_knowledge`를 통해 승격 명령을 내립니다.
    2.  엔진이 통찰을 선택하고 새로운 L2 Atom으로 원자화합니다.
    3.  Atom이 `02_Wiki/` (공식 Exhibition Hall)로 승격됩니다.
    4.  다음 수집 주기에서 이 통찰은 L1 파이프라인으로 재흡수되어 시스템의 기반 진실을 확장합니다.

---

## 4. 무결성 제약 조건

*   **조용한 폴백 금지**: 초기화 또는 워크스페이스 스코핑 중에 대상 경로가 유효한 Vault 내에 없는 경우 시스템은 절대로 `last_root`나 CWD로 폴백해서는 안 됩니다. 데이터 손상을 방지하기 위해 명시적으로 실패해야 합니다.
*   **불변성 계층구조**: 원본 소스(`03_Notes`)는 MCP 서버에 의해 절대 수정되지 않습니다. 모든 수정은 DAG(`.curator/`) 내부에서 일어나거나 `02_Wiki/`로의 승격을 통해 이루어집니다.

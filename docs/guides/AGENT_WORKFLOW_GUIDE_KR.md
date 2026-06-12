# Incurator 에이전트 워크플로우 가이드

이 문서는 Incurator MCP (Model Context Protocol) 서버의 공식 운영 시나리오와 도구 상호작용 패턴을 정의합니다. 높은 수준의 4단계 파이프라인 이론과 에이전트 또는 사용자의 명령에 의해 트리거되는 실제 실행 흐름을 연결합니다.

[English Guide](AGENT_WORKFLOW_GUIDE.md)

## 1. 환경 및 초기화 시나리오

### 1.1 세션 진입 및 동기화 (`curator_check_workspace`)
*   **트리거**: 모든 세션 시작 시 에이전트에 의해 자동으로 호출됩니다.
*   **논리 흐름**:
    1.  **경로 해석**: `workspace_path`에서 위로 이동하며 `vault_root`를 발견합니다.
    2.  **상태 검증**: `curate.yml` 존재 여부와 agent rule 준비 상태를 확인합니다.
    3.  **결과**: 초기화 필요 여부(`needs_initialization`), 프로젝트 메타데이터, 실행 가능한 설정 이슈를 반환합니다.

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
    1.  워크스페이스가 지정되면 `curate.yml`의 페르소나/KRS를 적용하고, Vault 모드는 글로벌 폴백 페르소나를 사용합니다.
    2.  선택된 L3 Concept, L4 Synthesis node, source section, report, insight candidate에 대한 `QTR-` trace와 함께 sessionless 답변을 반환합니다.
*   **논리 흐름 (`search_curator`)**:
    1.  로컬 `curate.yml`에서 `domains`, `topics`, `min_confidence` 필터를 자동으로 적용합니다.
    2.  authoritative record 위의 DB-native search row를 검색하며 staging pass를 트리거하지 않습니다.
    3.  프로젝트의 지식 요구사항으로 범위가 지정된 결과를 반환하여 Vault의 관련 없는 부분에서 발생하는 "지식 노이즈"를 방지합니다.

### 2.2 근거 추적 (`curator_traverse_evidence`)
*   **상황**: 검색 결과 신뢰도 점수가 높은 임계값(0.90)보다 낮지만 낮은 하한선(0.60)보다는 높은 경우.
*   **논리 흐름**:
    1.  에이전트가 증거 체인을 거슬러 올라갑니다: `SYN -> CON/REP -> ATM/source spans`.
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
    1.  Obsidian 플러그인은 현재 페이지 텍스트, 활성화된 현재 페이지 이미지, 인접 페이지 텍스트 창, 문서 목차, PDF-local lexical RAG hit 등 즉각적인 viewer context를 먼저 캡처합니다. 이 local PDF.js 경로는 backend status를 기다리지 않습니다.
    2.  local context가 충분하면 그것으로 답합니다. passive chat은 PDF를 import하거나 register하지 않습니다.
    3.  local context가 없을 때만 플러그인이 read-only source status를 확인하고 backend PDF context를 요청합니다. 미등록 PDF는 ephemeral parse를, 등록되고 L1이 완료된 PDF는 durable CTX section을 받습니다.
    4.  등록되고 L3까지 완료된 PDF만 PDF-focused `curator_query` 결과를 추가할 수 있습니다. backend evidence는 즉각적인 viewer context를 대체하지 않고 보완합니다.

### 2.5 MCP 상태 변경 규칙
*   **조용한 노트 편집 금지**: MCP 도구는 `03_Notes/`를 편집해서는 안 됩니다.
*   **직접적인 플러그인 상태 쓰기 금지**: 플러그인은 `.curator/state.sqlite`를 수정해서는 안 됩니다.
*   **명시적인 Vault 루트**: `VAULT_ROOT` 또는 명시적인 `workspace_path`/`vault_root` 인수는 반드시 유효한 Vault로 해석되어야 합니다. 해석에 실패할 경우, MCP는 CWD로 폴백하지 않고 오류를 반환해야 합니다.
*   **덮어쓰기 임포트 금지**: 소스 임포트가 `04_Resources/`에 있는 기존 파일을 덮어써서는 안 됩니다. 동일한 해시의 중복은 기존 레코드를 재사용하며, 해시가 다른 파일명 충돌은 접미사 또는 사용자가 선택한 대상을 필요로 합니다.
*   **파괴적인 모호성을 위한 사전 Dry-run**: rebind나 임포트 충돌 복구와 같이 영구적인 소스 정체성을 변경하는 모든 작업은 실제 상태 변경 전에 dry-run/제안 결과를 지원해야 합니다.

---

## 3. 지식 진화 및 무결성 시나리오

### 3.1 역전파 (지식 교정)
*   **상황**: 사람(Director) 또는 에이전트(Artist)가 생성된 지식에서 오류를 식별합니다.
*   **논리 흐름**:
    1.  에이전트가 claim, correction, evidence context와 함께 `curator_propose_correction`을 호출합니다.
    2.  엔진은 패치 전에 피드백을 분류합니다.
    3.  엔진은 자동 패치 없이 권장 동작과 영향받는 생성 노드 id를 반환하며, source truth는 자율적으로 편집하지 않습니다.
    4.  별도의 검토 workflow가 승인된 변경을 적용한 뒤 `wiki sync`로 그래프 일관성을 검증할 수 있습니다.

### 3.2 통합 승격 (무한 루프 - Path B)
*   **상황**: 대화 세션 중에 가치 있는 통찰이 도출됩니다.
*   **논리 흐름**:
    1.  사용자가 `curator_add_knowledge`를 통해 승격 명령을 내립니다.
    2.  엔진은 검토된 답변 또는 통찰을 `02_Wiki/`에만 기록합니다.
    3.  이후 별도의 명시적 ingest가 해당 노트를 등록할 때만 source material이 되며, 승격 자체는 생성 DAG를 변경하지 않습니다.

---

## 4. 무결성 제약 조건

*   **조용한 폴백 금지**: 초기화 또는 워크스페이스 스코핑 중에 대상 경로가 유효한 Vault 내에 없는 경우 시스템은 절대로 `last_root`나 CWD로 폴백해서는 안 됩니다. 데이터 손상을 방지하기 위해 명시적으로 실패해야 합니다.
*   **불변성 계층구조**: 원본 소스(`03_Notes`)는 MCP 서버에 의해 절대 수정되지 않습니다. 모든 수정은 DAG(`.curator/`) 내부에서 일어나거나 `02_Wiki/`로의 승격을 통해 이루어집니다.

---

## 5. Failure Atlas 진단 (Program 1)

Failure Atlas(`docs/specs/failure_atlas/FAILURE_ATLAS.md`)는 RAG/DAG 시스템의
알려진 모든 end-to-end 품질 결함(F1–F13)을 결정론적 재현과 동결된 오라클과
함께 기록한 버전 관리 문서입니다. 검색(retrieval), 컴파일러 파이프라인,
클라이언트 표면을 수정하는 에이전트는 해당 영역의 동작을 변경하기 전에 반드시
이 문서를 확인해야 합니다.

### 5.1 진단 스위트 실행

```bash
export UV_PROJECT_ENVIRONMENT="$(git rev-parse --show-toplevel)/.venv"
# Atlas 레코드 무결성 (스키마, 라이프사이클, 스냅샷 식별자)
uv run --directory backend pytest tests/test_failure_atlas_contract.py -q
# 결정론적 재현 (baseline + strict-xfail 오라클)
uv run --directory backend pytest tests/test_failure_atlas_repro.py -q
# 변이/성능저하/원자성 실험
uv run --directory backend pytest tests/test_failure_atlas_experiments.py -q
# 동결된 검색 베이스라인 (CI는 D2에서 소비한 holdout을 다시 실행하지 않음)
uv run --directory backend pytest tests/test_failure_atlas_eval.py -q
```

### 5.2 변경 사항이 Atlas 케이스에 닿을 때의 규칙

*   **Baseline 테스트는 현재 동작을 고정합니다**: `test_f*_baseline_*`가
    통과한다는 것은 문서화된 결함이 여전히 존재한다는 뜻입니다. 변경으로 인해
    baseline 테스트가 실패하면 측정된 동작이 바뀐 것이므로, 같은 커밋에서
    해당 `docs/specs/failure_atlas/cases/F*.yml` 레코드를 갱신해야 합니다.
*   **Oracle 테스트는 핸드오프 장치입니다**: `test_f*_oracle_*`는
    `xfail(strict=True)`입니다. 결함을 고치면 해당 오라클이 XPASS가 되어
    의도적으로 CI가 실패합니다. 고치는 커밋에서 마커를 제거하고, 케이스
    레코드의 status를 새 `status_history` 항목과 함께 전환하고, baseline
    테스트를 갱신해야 합니다. 통과시키기 위해 오라클을 약화시키는 것은
    금지이며, 오라클 재협상은 `FAILURE_ATLAS.md` §3에 따라 새 atlas 버전이
    필요합니다.
*   **수리 전 캡처(capture before repair)**: 현재 결함 베이스라인이 atlas에
    캡처되기 전에는 어떤 프로덕션 동작도 수리할 수 없습니다.
*   **Holdout 튜닝 금지**: `docs/specs/failure_atlas/qrels.yml`의 `holdout`
    파티션 쿼리는 동결 상태이며 검색 변경의 개발이나 튜닝에 절대 사용해서는
    안 됩니다. D2는 동일한 동결 ranking 설정에서 방법론 감사로 무효화된
    실행 2회 후 유효한 `Q06` 결과 1회를 기록했으며, CI는
    `D2_HOLDOUT_RESULT.yml`을 검증할 뿐 다시 실행하지 않습니다.
*   **세분화된 게이트 사용**: Recall@k, MRR, 인용 정확도와 완전성,
    provenance 해소율, hard-negative outrank 수, 비용, 지연 시간을 쿼리
    패밀리별로 각각 보고해야 합니다. 집계 수치만으로는 릴리스 근거가 될 수
    없습니다.

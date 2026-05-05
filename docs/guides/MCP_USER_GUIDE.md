# 🔌 MCP 사용법 가이드: 에이전트 연결하기


**InCurator MCP 서버**를 사용하면 Claude Desktop, Claude Code, Gemini CLI 등 워크스페이스 내의 에이전트가 지식 DAG 및 검색 인덱스와 직접 상호작용할 수 있습니다.

[English Guide](MCP_USER_GUIDE_EN.md)

---

## 1. 사전 요구 사항

MCP 의존성 패키지가 설치되어 있는지 확인하세요.
```bash
uv pip install -e '.[mcp]'
```

> [!NOTE]
> 서버는 `WIKI_ROOT` 환경 변수를 참조하여 저장소 위치를 찾습니다. 설정되지 않은 경우 현재 디렉토리에서 상위로 이동하며 저장소를 자동 탐색합니다.

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
    "incurator": {
      "command": "wiki",
      "args": ["mcp"],
      "env": {
        "WIKI_ROOT": "/저장소/절대/경로"
      }
    }
  }
}
```

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

#### `curator_add_knowledge`
- **역할**: 대화 중 얻은 통찰을 새로운 **L2 Atom**으로 저장합니다. 이 지식은 다음 큐레이션 주기에서 DAG에 합성됩니다.

#### `curator_update_node`
- **역할**: 특정 노드의 내용을 업데이트합니다.
- **자동 수리 (Backprop)**: **Exhibition (EXH)** 노드를 수정할 경우, 내부적으로 `wiki sync`가 작동하여 상위 Concept과 Atom으로 변경 사항을 자동 전파하고 재작성합니다. 이를 통해 대화 중 발견된 오류를 즉시 시스템에 반영하고 지식을 강화할 수 있습니다.

#### `curator_reindex`
- **역할**: QMD 검색 인덱스를 수동으로 다시 빌드합니다.

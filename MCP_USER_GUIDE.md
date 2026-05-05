# LLM-Wiki MCP 사용법 유저 가이드

`llm_wiki` MCP(Model Context Protocol) 서버를 사용하면 **Claude Desktop**, **Claude Code**, **Gemini CLI** 등 작업 공간 내의 에이전트가 LLM-Wiki의 지식 그래프(DAG) 및 검색 인덱스에 직접 접근하고 상호작용할 수 있습니다.

이 가이드는 `llm_wiki` MCP 서버의 설치, 연동 및 제공되는 주요 도구(Tools) 사용법을 안내합니다.

---

## 1. 사전 요구 사항 (Prerequisites)

MCP 서버를 실행하기 전에 `llm_wiki` 프로젝트에 MCP 관련 패키지가 설치되어 있어야 합니다.

```bash
# 프로젝트의 MCP 의존성 패키지 설치
uv pip install -e '.[mcp]'
```

> [!NOTE]
> MCP 서버는 실행 시 환경 변수 `WIKI_ROOT`를 참조하여 지식 저장소(Vault)의 위치를 확인합니다. `WIKI_ROOT`가 설정되지 않은 경우, 현재 작업 디렉토리(`cwd`)에서 상위 폴더로 이동하며 지식 저장소를 자동으로 탐색합니다.

---

## 2. 클라이언트 연동 설정 (Configuration)

`wiki mcp install` 명령어를 실행하면 사용자의 클라이언트에 맞춰 복사하여 붙여넣을 수 있는 설정 스니펫을 생성해 줍니다.

```bash
wiki mcp install
```

특정 클라이언트용 스니펫만 출력하려면 다음과 같이 실행할 수 있습니다.
- `wiki mcp install claude`
- `wiki mcp install gemini`

출력된 JSON 스니펫을 클라이언트별 설정 파일에 추가합니다.

### 2.1 Claude Code / Claude Desktop 연동

**Claude 설정 파일 위치:**
- **Claude Code**: `~/.claude/settings.json`
- **Claude Desktop (macOS)**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Claude Desktop (Windows)**: `%APPDATA%\Claude\claude_desktop_config.json`

**설정 스니펫 예시:**
```json
{
  "mcpServers": {
    "llm-wiki": {
      "command": "wiki",
      "args": ["mcp"],
      "env": {
        "WIKI_ROOT": "/home/shin/Workspace/llm_wiki"
      }
    }
  }
}
```

### 2.2 Gemini CLI 연동

**Gemini 설정 파일 위치:**
- **Gemini CLI**: `~/.gemini/settings.json`

**설정 스니펫 예시:**
```json
{
  "mcpServers": {
    "llm-wiki": {
      "command": "wiki",
      "args": ["mcp"],
      "env": {
        "WIKI_ROOT": "/home/shin/Workspace/llm_wiki"
      }
    }
  }
}
```

### 2.3 Antigravity 연동

**Antigravity 설정 파일 위치:**
- **Antigravity**: `/home/shin/.gemini/antigravity/mcp_config.json`

**설정 스니펫 예시:**
```json
{
  "mcpServers": {
    "llm-wiki": {
      "command": "wiki",
      "args": ["mcp"],
      "env": {
        "WIKI_ROOT": "/home/shin/Workspace/llm_wiki"
      }
    }
  }
}
```

> [!TIP]
> 설정 파일을 수정하고 나면 MCP 클라이언트를 **반드시 재시작**해야 변경 사항이 적용됩니다.

---


## 3. 제공되는 MCP 도구 (Tools)

연동이 완료되면 에이전트가 다음 도구들을 호출하여 지식 저장소를 탐색 및 수정할 수 있습니다.

### 3.1 검색 및 메타 데이터 조회

#### `search_curator`
- **역할**: QMD 검색 엔진을 사용하여 지식 저장소 전체를 대상으로 검색합니다.
- **파라미터**:
  - `query` (string): 검색할 자연어 쿼리
  - `scope` (string): `'all'` | `'accessions'` | `'fragments'` | `'themes'` | `'curations'`
  - `mode` (string): `'hybrid'` (기본값, 고품질) | `'lex'` (BM25 전용, 고속) | `'vec'` (Vector 전용)
  - `limit` (integer): 최대 검색 결과 수 (기본값: 8)
  - `min_score` (float): 검색 최소 점수 제한

#### `curator_get_node`
- **역할**: 특정 ID의 지식 노드를 파일에서 읽어 반환합니다.
- **파라미터**: `node_id` (예: `CUR-abcdef01`, `FRG-9f8e7d6c`, `THM-12345678`, `ACC-01234567`)

#### `curator_layer_index`
- **역할**: 각 레이어별(Accessions, Fragments, Themes, Curations) 페이지 수와 최근 노드 샘플 ID를 조회합니다. 에이전트가 저장소의 전반적인 상태를 빠르게 훑을 때 유용합니다.

#### `curator_status`
- **역할**: 지식 저장소의 경로, 총 페이지 수, QMD 검색 엔진의 준비 여부 및 버전을 반환합니다.

---

### 3.2 지식 그래프(DAG) 분석 및 순회

#### `curator_traverse_evidence`
- **역할**: Curation 노드를 기준으로 그 하위에 속한 모든 Theme 노드와 Fragment 노드의 전체 증거 체인을 순회하여 조회합니다.
- **파라미터**: `cur_id` (예: `CUR-abcdef01`)

#### `curator_find_contradictions`
- **역할**: 에이전트가 충돌하는 주장이나 검토가 필요하여 플래그(`is_flagged_for_agent`)가 지정된 Fragment 또는 모순 항목(`contradicts`)이 존재하는 Fragment를 검색합니다.
- **파라미터**: `node_id` (optional, 특정 하위 그래프만 탐색할 경우 지정)

---

### 3.3 지식 저장소 갱신 및 관리

#### `curator_update_node`
- **역할**: 특정 노드의 마크다운 내용(프론트매터 및 본문)을 덮어쓰고, 상향/하향식 Deductive Verification 전파(Mode B)를 수행합니다.
- **파라미터**:
  - `node_id` (string): 업데이트할 노드 ID
  - `new_content` (string): 변경할 전체 마크다운 텍스트

#### `curator_reindex`
- **역할**: 지식 저장소의 모든 페이지를 대상으로 QMD 검색 인덱스를 새로 빌드합니다. 대량 추가나 직접 파일 수정을 한 후 호출합니다.

#### `curator_curate_accession`
- **역할**: 특정 Accession의 LLM 큐레이션 파이프라인(L1 → L2 → L4)을 백그라운드에서 다시 실행합니다.
- **파라미터**: `accession_id` (예: `ACC-01234567`)

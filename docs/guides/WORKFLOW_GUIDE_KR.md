# Incurator 전체 워크플로우

> 이 문서는 Incurator 시스템을 구성하는 세 가지 요소가 어떻게 맞물려 동작하는지 설명합니다.

[English Guide](WORKFLOW_GUIDE.md)

---

## 1. 시스템 구성 요소

Incurator는 세 개의 독립적인 구성 요소로 이루어집니다.

```text
┌─────────────────────────────────────────────────────┐
│                   Obsidian Vault                    │
│                                                     │
│  ┌──────────────────────┐   ┌─────────────────────┐ │
│  │  Obsidian Plugin     │   │  .curator/ (백엔드)  │ │
│  │  (incurator-agent)   │◄──►  Collections/       │ │
│  │  - 채팅 사이드바      │   │  L1 ~ L4 DAG        │ │
│  │  - 인라인 편집        │   │  state.sqlite       │ │
│  │  - PDF 컨텍스트       │   └──────────┬──────────┘ │
│  └──────────┬───────────┘              │            │
│             │ MCP                      │ wiki CLI   │
└─────────────┼──────────────────────────┼────────────┘
              │                          │
              ▼                          ▼
   ┌─────────────────────┐   ┌───────────────────────┐
   │  AI Agent (MCP)     │   │  wiki 명령어           │
   │  Claude Code        │   │  wiki add / curate    │
   │  Antigravity        │   │  wiki sync / query    │
   │  Codex              │   │  wiki status / lint   │
   └─────────────────────┘   └───────────────────────┘
```

| 구성 요소 | 역할 | 진입점 |
|-----------|------|--------|
| **Curator 백엔드** | 소스 수집, 4-레이어 DAG 구축, 검색 | `wiki` CLI |
| **Obsidian 플러그인** | Obsidian 내 AI 채팅·편집·PDF 처리 | Obsidian 내 UI |
| **Agent MCP 서버** | AI 에이전트(Claude Code 등)에게 Curator 도구 노출 | `wiki mcp` |

---

## 2. Vault 위치 구조

Incurator에서 **세 가지 경로**를 구분하는 것이 중요합니다.

| 경로 | 역할 | 예시 |
|------|------|------|
| **Wiki system** | `wiki` CLI 코드가 위치한 곳 | `/path/to/incurator/` |
| **Vault** (`VAULT_ROOT`) | raw 파일과 `.curator/`가 상주하는 곳 | `/path/to/vault/` |
| **Workspace** | 프로젝트별 `curate.yml`이 있는 곳 | `<vault>/01_Workspaces/MyProject/` |

`VAULT_ROOT` 환경 변수 또는 MCP 설정의 `env.VAULT_ROOT`는 항상 **Vault 경로**를 가리켜야 합니다.

---

## 3. 4-레이어 DAG 구조

Incurator는 소스 문서를 4단계 추상화 레이어로 처리합니다.

```text
[소스 파일]  (03_Notes/, 04_Resources/, 02_Wiki/ 등)
     │
     │  wiki add
     ▼
[L1: Contexts]  (DB 레코드: source_spans)
  - 소스 1개당 1개의 컨텍스트 요약
  - 원본 내용, 메타데이터, 해시 연결
     │
     │  wiki build (L2 pass)
     ▼
[L2: Atoms]  (DB 레코드: knowledge_units)
  - L1에서 추출한 원자적 지식 단위
  - 하나의 사실·주장·결론
  - 검증 근거(인용) 포함
     │
     │  wiki build (L3 pass)
     ▼
[L3: Concepts]  (DB 레코드: graph_entities/relations)
  - 여러 소스의 Atom을 묶은 주제 클러스터
  - 크로스-소스 비교·통합
     │
     │  wiki curate --workspace <path>
     ▼
[L4: Exhibitions]  .curator/Collections/04_Exhibitions/EXH-UUID.md
  - 특정 Workspace의 curate.yml 기준으로 패키징된 최종 컨텍스트
  - Agent가 소비하는 터미널 단위
  - 에이전트 검색의 1차 소스
```

---

## 4. 핵심 워크플로우

### 4-1. 소스 수집 및 DAG 구축

```bash
# 1. Vault 초기화 (최초 1회)
wiki init /path/to/vault

# 2. 소스 추가 (wiki add) — 등록 + 즉시 L1만 (LLM 없음)
#    특정 파일 또는 디렉토리 전체
wiki add 03_Notes/paper.pdf
wiki add 04_Resources/

# 내부 동작 (Math-Aware v0.2.2):
#   - SHA-256 해시로 중복 감지
#   - 하이브리드 파이프라인: 기본은 pymupdf4llm(Markdown)으로 변환, 필요 시 VLM 파서 연동
#   - AST 기반 청킹: 수학 수식 블록($$...$$)을 보호하여 텍스트 분할
#   - L1 Context 파일을 구조로부터 즉시 생성 → 즉시 반환
#   - LLM 호출 없음; L1이 만들어지면 곧바로 검색(BM25) 가능

# 3. L2/L3 빌드 (wiki build) — 깊은 LLM 추출 단계
wiki build            # L2/L3를 백그라운드 워커에 큐잉 (논블로킹)
wiki build --wait     # L2(Atoms) → L3(Concepts)를 지금 동기 실행
#   - 진행 상황: .curator/dashboard.md 실시간 업데이트 (Obsidian에서 바로 확인)
```

> **2단계 수집**: `wiki add`는 소스를 등록하고 즉시 L1을 생성한다(구조 기반, LLM 없음) —
> 빠르고 오프라인에서도 동작한다. `wiki build`는 깊은 L2/L3 추출을 수행하며, 기본은 MCP 서버의
> 백그라운드 IngestWorker에 큐잉하고 `--wait`로 즉시 실행할 수 있다. L2 추출은 활성 LLM
> 클라이언트의 prompt budget에 맞춰 section batch 크기를 정하므로, CLI 기반 provider에는
> local high-context 모델보다 작은 prompt가 전달된다. 진행률은 `wiki status`나
> `.curator/dashboard.md`로 확인한다. L4 Exhibition은 보통 필요 시 workspace
> agent 흐름에서 생성된다. 수동 `wiki curate` 명령은 기본 help에서 숨겨진
> 고급/디버깅용 workspace curation 경로다.

### 4-2. 고급 Workspace 큐레이션

```bash
# Workspace 폴더에 curate.yml 생성 (직접 또는 wiki workspace init)
# curate.yml 핵심 필드:
#   vault_root: /path/to/vault   ← Vault 경로
#   sources.include: ["03_Notes/**", "04_Resources/**"]
#   min_confidence: 0.70

# L4 Exhibition 생성
wiki curate --workspace 01_Workspaces/MyProject
```

`wiki curate`는 workspace-agent 및 디버깅 워크플로우를 위해 직접 호출 가능하지만,
일반 사용자용 `wiki --help` 표면에는 포함하지 않는다.

### 4-3. 검색 및 질의

```bash
# 자연어 질의 (BM25 + vector + LLM rerank + 동적 2-Step RAG)
wiki query "Gaussian Splatting에서 COLMAP 없이 카메라 포즈를 추정하는 방법은?"

# 명시적 Workspace를 지정한 질의 (Pinned Exhibition 모드)
wiki query --workspace 01_Workspaces/MyProject "우리의 목표를 요약해줘."

# 검색 인덱스 재구축
wiki reindex

# 전체 상태 확인 (백그라운드 잡 진행률 포함)
wiki status

# DAG 무결성 검사 (v0.2.1 — 기본값: hash 기반 증분 검사)
wiki sync              # 기본: 변경 노드만 재검증 (~1초, 변경 없을 시)
wiki sync --full       # 전체 재검증 (v0.2.0 이전 동작)
wiki sync --backward   # 특정 노드 역전파 수동 트리거
wiki lint

# MCP 서버가 꺼져 있거나 즉시 처리하고 싶을 때
wiki jobs list
wiki jobs run          # queued L2/L3 background jobs를 foreground로 처리
wiki jobs cancel <id>  # worker가 claim하기 전 queued job 취소
wiki jobs rerun <id>   # 완료/실패/취소된 job을 다시 queue에 넣기
```

기본 `wiki --help` 화면은 일상적인 사용자 워크플로우 중심으로 제한됩니다.
통합/개발용 명령은 직접 호출할 수 있지만 일반 help 목록에서는 숨깁니다:
Obsidian plugin JSON 호출용 `wiki plugin ...`, 외부 에이전트용 `wiki mcp ...`,
개발 fixture용 `wiki testbed ...`, backend launcher 진단용 `wiki devices ...`.

> **wiki sync 기본 동작 변경 (v0.2.1)**: 변경되지 않은 DAG에서 `wiki sync`는 content_hash 검사만 수행합니다(~0.6초).
> 변경된 노드와 그 하위 노드만 LLM으로 재검증됩니다. 전체 재검증을 원하면 `--full`을 사용하세요.

> **이원화된 질의 아키텍처 및 Exhibition 영구 보존**:
> - **Workspace Agent**: 워크스페이스가 지정되면, `curate.yml`에 정의된 **Pinned Exhibition**과 페르소나를 사용하며, 채팅용 임시 파일을 생성하지 않습니다.
> - **Vault Agent**: 일반 Vault 질의 시에는 세션별로 **영구적인 L4 Exhibition**을 동적으로 생성하고, 글로벌 폴백 페르소나를 사용합니다.
> - **L3 제약 조건**: L4 Exhibition은 검색된 **L3 Concept이 있을 때만 생성**됩니다. 일치하는 L3가 없으면 L4를 저장하지 않고 즉시 답변합니다.
> - **Exhibition 생명주기 (v0.3.1)**: 채팅으로 생성된 Exhibition은 사용자의 성향과 세션 기록을 종합하는 "살아있는 문서(Living Document)" 역할을 합니다. 기존의 24시간 임시 GC 룰은 폐기(Deprecated)되었으며, 이제 이 Exhibition들은 고품질의 최종 전시품으로 영구 보존됩니다.

> **백그라운드 워커 폴백**: MCP 서버가 실행 중일 때 IngestWorker가 대기 중인 작업을 자동으로 처리합니다.
> 테스트나 오프라인 CLI 사용 시에는 `wiki jobs run` 명령으로 큐를 전경(foreground)에서 처리할 수 있습니다.
> 실행하지 않을 queued job은 `wiki jobs cancel <id>`로 취소하고, 완료/실패/취소된 job은
> `wiki jobs rerun <id>`로 다시 queue에 넣을 수 있습니다.

> **즉각적인 L1 / L2·L3 분리**: `wiki add`는 LLM 호출 없이 파서 구조로부터 즉시 CTX, ToC, 섹션 마커 및
> 대략적인 Atom 후보를 생성합니다(구조적 L1). v0.2.2부터 이 단계는 **AST 기반 청킹**을 사용해
> `$$...$$` 같은 수학 수식 블록을 텍스트 분할 중에도 보존합니다. 깊은 L2/L3 추출은 `wiki add`와
> 분리되어 별도의 `wiki build` 명령으로 수행됩니다. 기본 동작은 백그라운드 작업 큐에 넣는 것이고,
> `--wait`는 동기 실행을 요청합니다. MCP에서는 `curator_register_source`가 L1 등록을 담당하고
> `curator_build_source`가 L2/L3 빌드에 대응합니다.

> **v0.2.1 성능 경로**: LLM 클라이언트를 안전하게 복제할 수 있는 경우 L2는 다중 섹션 인식 배치를 병렬로 실행합니다.
> L3는 임베딩 기반 클러스터링을 먼저 시도하고, 임베딩 경로가 없을 때만 기존 LLM 클러스터링 계획으로 폴백합니다.
---

## 5. Obsidian 플러그인 워크플로우

플러그인은 Obsidian 내에서 AI 어시스턴트로 동작하며, 선택적으로 Curator 백엔드와 연동합니다.

```text
Obsidian 플러그인 단독 사용:
  사용자 채팅 → LLM 직접 호출 (Antigravity/Claude/OpenAI/DeepSeek/Ollama)

Curator 백엔드 연동 사용:
  사용자 채팅 → 플러그인이 MCP 도구 호출 → Curator가 Exhibition 검색
              → LLM이 Exhibition 내용을 근거로 답변 생성
```

### PDF 처리 흐름 (v0.2.1 — Adaptive Routing)

```text
Obsidian에서 PDF 열기
     │
     │ check_source_status(file_hash) 자동 호출
     ▼
┌─── 미등록 ────────────────────────────────────────────────────┐
│ ephemeral L1 모드: PDF.js in-memory 파싱                       │
│ 플러그인 UI: "+ Add to Incurator" 버튼                         │
│ 에이전트: fetch_document_section(source_key, toc_id)로 섹션 읽기│
└───────────────────────────────────────────────────────────────┘
     │ (사용자가 "+ Add" 클릭 또는 import_source 호출)
     ▼
┌─── 처리 중 ──────────────────────────────────────────────────┐
│ 외부 PDF: 04_Resources markdown reference stub 생성             │
│ 플러그인 UI: "⟳ Processing" 상태 표시                          │
│ 5초 간격 재폴링 → l3_complete=True 되면 자동 업그레이드         │
│ l1_complete=True 시점부터 fetch_document_section은 CTX 섹션 사용 │
└───────────────────────────────────────────────────────────────┘
     │ (L3 처리 완료)
     ▼
┌─── 인덱싱 완료 ───────────────────────────────────────────────┐
│ 플러그인 UI: "✓ Indexed (47 atoms · 8 concepts)"              │
│ 에이전트: curator_query("질문", workspace_id="...") 사용 가능   │
└───────────────────────────────────────────────────────────────┘
     │
     │ workspace curation 실행 (필요 시)
     ▼
L4 Exhibition 생성 → search_curator로 검색 가능
```

---

## 6. Agent 워크플로우

Agent 접근 경로는 두 가지로 분리합니다:

- **같은 기기 안의 Obsidian plugin agent**는 shared runtime snapshot과 숨겨진
  `wiki plugin ...` JSON command를 사용합니다. 로컬 backend 접근을 위해
  `wiki mcp`를 시작하지 않습니다.
- **외부 workspace agent**(Claude Code, Claude Desktop, Antigravity 등 MCP
  client)는 `wiki mcp`를 사용합니다.

두 경로를 섞지 않습니다. 같은 기기 안의 Obsidian plugin 기능은
`wiki plugin ...` 아래에 추가하고, 외부 agent 기능은 MCP server에 추가합니다.

### 외부 Agent(MCP) 워크플로우

Claude Code, Antigravity 같은 AI 에이전트는 MCP 서버를 통해 Curator에 접근합니다.

#### MCP 서버 시작

```bash
# Vault를 지정해서 MCP 서버 실행
VAULT_ROOT=/path/to/vault wiki mcp

# 또는 MCP 클라이언트 설정에서 env로 지정:
# {
#   "mcpServers": {
#     "incurator": {
#       "command": "wiki",
#       "args": ["mcp"],
#       "env": { "VAULT_ROOT": "/path/to/vault" }
#     }
#   }
# }
```

### 에이전트 세션 흐름

```text
에이전트 세션 시작
     │
     │ 1. curator_check_workspace(workspace_path)
     │    → curate.yml 유효성, 에이전트 룰 설치, Exhibition 존재 확인
     ▼
도메인 질의 발생
     │
     │ 2. search_curator(query, workspace_path)
     │    → Exhibition 기반 BM25+벡터 검색
     │    → 결과가 없으면 workspace curation을 트리거할 수 있음
     ▼
답변 생성 (검색 결과 인용)
     │
     │ (선택) 새 소스 발견 시
     │ 3. curator_add_knowledge(content, source_type)
     │    → Atom 생성 → 인덱스 자동 갱신
     ▼
세션 종료
     │
     │ 4. (optional) curator_curate_workspace
     │    → Exhibition 갱신
```

### 주요 MCP 도구

| 도구 | 용도 |
|------|------|
| `curator_check_workspace` | 세션 시작 시 Workspace 상태 점검 및 룰 설치 |
| `search_curator` | 자연어 검색 (Exhibition 기반) |
| `curator_workspace_init` | 새 Workspace 생성 (인터뷰 방식) |
| `curator_curate_workspace` | 현재 Workspace의 L4 Exhibition 재생성 |
| `curator_add_knowledge` | 새 지식 단위(Atom) 직접 추가 |
| `curator_update_node` | 기존 DAG 노드 수정 및 propagation |
| `curator_get_node` | 특정 노드(CTX/ATM/CON/EXH) 내용 조회 |

---

## 6-1. 백그라운드 처리 모니터링

`wiki add` 이후 L2/L3 처리는 MCP 서버의 IngestWorker 스레드가 비동기로 수행한다.
진행 상황을 확인하는 방법은 세 가지다.

### 방법 1: .curator/dashboard.md (Obsidian)

IngestWorker가 자동으로 갱신하는 파일로, Obsidian live preview에서 실시간 확인 가능하다.

```text
# Incurator Build Status
*2026-05-29T14:32:07Z*

## Active
| Source         | Phase       | Progress |
|----------------|-------------|----------|
| paper_xyz.pdf  | l3_concepts | 3/5      |

## Queue
| Source         | Phase    |
|----------------|----------|
| new_paper.pdf  | l2_atoms |

## Completed Today
2 jobs · 47 atoms · 8 concepts
Cost: $0.043
```

### 방법 2: wiki status (CLI)

```bash
wiki status
# Background jobs 섹션에서 진행 중인 잡 목록 확인
```

### 방법 3: 플러그인 상태 바

Obsidian 하단 상태 바에 `⚡ 2 running / 1 queued` 형태로 표시.
클릭 시 `dashboard.md`를 Obsidian에서 오픈.

---

## 7. 설치 흐름

```bash
# 1. 저장소 클론
git clone https://github.com/your/incurator.git
cd Incurator

# 2. 전체 설치 (백엔드 + 플러그인)
./setup.sh

# 3. Vault 초기화
wiki init /path/to/your/vault

# 4. MCP 설정 자동 갱신 (setup.sh이 처리하거나 수동으로)
#    wiki init 실행 시 아래 파일들을 자동 갱신:
#    - ~/.antigravity/settings.json
#    - ~/.antigravity/mcp_config.json
#    - <vault>/.claude/settings.json

# 5. 소스 추가 및 큐레이션
wiki add 03_Notes/
wiki curate --workspace 01_Workspaces/MyProject

# 6. 검색 확인
wiki query "첫 번째 질문"
```

---

## 8. 데이터 흐름 요약

```text
[Human Layer]
  03_Notes/ ──┐
  04_Resources/ ──┤── wiki add ──► L1 CTX ──► L2 ATM ──► L3 CON
  02_Wiki/ ───┘                                              │
                                                             │ wiki curate
[Machine Layer (state.sqlite DB)]                            ▼
  .curator/Collections/04_Exhibitions/ ◄─────── L4 EXH (workspace-scoped)
                    │
         ┌──────────┼──────────┐
         ▼          ▼          ▼
    wiki query  MCP Agent  Obsidian Plugin
   (CLI 검색)  (AI 에이전트) (채팅 사이드바)
```

---

## 9. v0.3.1 큐레이션-네이티브 컴파일 모델

v0.3.1은 Curator를 **컴파일러**로 만듭니다. 중간 표현(IR)은 DB이고, 마크다운
컬렉션은 거기서 파생된 일회용 검색 코퍼스입니다.

- **`state.sqlite`가 큐레이션 지식의 유일한 진실원**입니다: `source_spans`,
  `knowledge_units`, `graph_entities`/`graph_relations`, `community_reports`,
  `memory_paths`, 의존성, 프롬프트 실행, 인사이트 후보.
- **`.curator/Collections/`의 L1–L3 마크다운(CTX/ATM/CON)은 DB에서 emit**되어
  `qmd`가 하이브리드 검색용으로 인덱싱합니다. 권위가 없고 언제든 재생성 가능 →
  DB↔파일 드리프트 없음.
- **사람/에이전트에 노출되는 건 L4 Exhibition뿐**(`02_Wiki/`로 출력)이며, 편집 시
  DB로 역파싱됩니다.

전방 컴파일 흐름:

```text
wiki add   → 파싱(LLM 없음) → DB source_spans              → CTX projection emit
wiki build → LLM            → DB knowledge_units            → ATM projection emit
           → LLM+임베딩      → DB entities/relations/reports → CON projection emit
           → qmd update/embed가 .curator/Collections/ 인덱싱
wiki query → 라우트 → qmd 검색(파생 코퍼스) + DB 그래프 탐색 → L4 EXH
```

### 9.1 쿼리 라우트

`wiki query "..." --route <route>` 는 v0.3.1 `QueryOrchestrator`로 답합니다:
`local`(엔티티/사실), `global`(커뮤니티 리포트), `explore`(메모리 경로 + 인사이트
후보), `exhibition`(활성 staged 컨텍스트), `source-section`(특정 원본). `--route`
없으면 레거시 qmd 경로(qmd는 폴백 엔진). 동일 라우팅이 MCP `curator_query` /
`curator_explore`로 에이전트에도 제공됩니다.

### 9.2 백프롭 & 인사이트 라이프사이클 (역방향 패스)

사람/에이전트 피드백은 **loss signal**입니다. 역방향 패스는 패치 전에 변경을
분류하고 원본 진실을 보호합니다:

- `wiki sync <EXH-ID> --backward [--dry-run]` 는 편집된 Exhibition을 역파싱하고
  분류(correction / contradiction / derived_insight / style_only /
  promotion_request / ambiguous)한 뒤 안전한 액션을 산출 — 파생 인사이트는 잠정
  **인사이트 후보**가 되고, 정정은 **생성된 노드에만** 대한 명시적 패치 플랜을
  만듭니다. `03_Notes/`/`04_Resources/`는 절대 수정하지 않습니다.
- 에이전트는 MCP `curator_propose_correction`으로 동일하게 수행합니다.
- `wiki insight list|show|promote`(또는 MCP `curator_list_insight_candidates` /
  `curator_promote_insight`)로 후보를 검토하며, 승격은 `02_Wiki/`에만 기록합니다.

### 9.3 프롬프트 추적성

모든 LLM 호출은 등록된 버전 있는 프롬프트 계약이며 `prompt_runs`(`PTR-`) 트레이스
(모델, 검증자 상태, 입출력 해시)를 남깁니다. `wiki prompt list|show|trace|eval`
또는 MCP `curator_get_prompt_trace`로 검사합니다. 모든 쿼리는 라우트·증거·프롬프트
실행을 잇는 `QTR-` 트레이스를 기록합니다.

---

## 관련 문서

- [플러그인 가이드](PLUGIN_GUIDE_KR.md) — Obsidian 플러그인 기능 상세
- [MCP 사용 가이드](MCP_USER_GUIDE_KR.md) — AI 에이전트 MCP 연결 설정
- [사용자 가이드](USER_GUIDE_KR.md) — CLI 명령어 레퍼런스
- [시스템 철학](../philosophy/ABOUT_KR.md) — Curator/Artist 메타포 배경

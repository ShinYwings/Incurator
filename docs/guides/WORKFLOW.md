# Incurator 전체 워크플로우

> 이 문서는 Incurator 시스템을 구성하는 세 가지 요소가 어떻게 맞물려 동작하는지 설명합니다.

[English Guide](WORKFLOW_EN.md)

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
   │  Gemini CLI         │   │  wiki sync / query    │
   │  Antigravity        │   │  wiki status / lint   │
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
[L1: Contexts]  .curator/Collections/01_Contexts/CTX-UUID.md
  - 소스 1개당 1개의 컨텍스트 요약
  - 원본 내용, 메타데이터, 해시 연결
     │
     │  wiki add (Phase A)
     ▼
[L2: Atoms]  .curator/Collections/02_Atoms/ATM-UUID.md
  - L1에서 추출한 원자적 지식 단위
  - 하나의 사실·주장·결론
  - 검증 근거(인용) 포함
     │
     │  wiki add (Phase B)
     ▼
[L3: Concepts]  .curator/Collections/03_Concepts/CON-UUID.md
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

# 내부 동작:
#   - SHA-256 해시로 중복 감지
#   - PyMuPDF(PDF) / 정규식(MD) / BeautifulSoup(HTML)로 파싱 + 이미지 추출
#   - L1 Context 파일을 구조로부터 즉시 생성 → 즉시 반환
#   - LLM 호출 없음; L1이 만들어지면 곧바로 검색(BM25) 가능

# 3. L2/L3 빌드 (wiki build) — 깊은 LLM 추출 단계
wiki build            # L2/L3를 백그라운드 워커에 큐잉 (논블로킹)
wiki build --wait     # L2(Atoms) → L3(Concepts)를 지금 동기 실행
#   - 진행 상황: .curator/dashboard.md 실시간 업데이트 (Obsidian에서 바로 확인)
```

> **2단계 수집**: `wiki add`는 소스를 등록하고 즉시 L1을 생성한다(구조 기반, LLM 없음) —
> 빠르고 오프라인에서도 동작한다. `wiki build`는 깊은 L2/L3 추출을 수행하며, 기본은 MCP 서버의
> 백그라운드 IngestWorker에 큐잉하고 `--wait`로 즉시 실행할 수 있다. 진행률은 `wiki status`나
> `.curator/dashboard.md`로 확인한다. L4 Exhibition은 별도 `wiki curate` 명령으로 생성한다.

### 4-2. Workspace 큐레이션

```bash
# Workspace 폴더에 curate.yml 생성 (직접 또는 wiki workspace init)
# curate.yml 핵심 필드:
#   vault_root: /path/to/vault   ← Vault 경로
#   sources.include: ["03_Notes/**", "04_Resources/**"]
#   min_confidence: 0.70

# L4 Exhibition 생성
wiki curate --workspace 01_Workspaces/MyProject
```

### 4-3. 검색 및 질의

```bash
# 자연어 질의 (BM25 + vector + LLM rerank)
wiki query "Gaussian Splatting에서 COLMAP 없이 카메라 포즈를 추정하는 방법은?"

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
```

> **wiki sync 기본 동작 변경 (v0.2.1)**: 변경 없는 DAG에서 `wiki sync` 실행 시
> content_hash 스캔만 수행 (~0.6초). 변경된 노드와 다운스트림만 LLM 재검증.
> 전체 재검증이 필요한 경우 `--full` 플래그를 사용한다.

> **백그라운드 워커 보강**: MCP 서버가 실행 중이면 IngestWorker가 queued job을 자동 처리한다.
> 서버가 꺼져 있거나 테스트/디버깅 중에는 `wiki jobs run`으로 같은 큐를 foreground에서 처리한다.

> **즉시 L1 / L2·L3 분리**: `wiki add`는 항상 LLM 호출 없이 parser 구조로 CTX, ToC,
> section marker, coarse Atom Candidates를 즉시 생성하고 반환한다(구조 기반 L1). 깊은
> L2/L3 추출은 `wiki add`에서 분리되어 별도 `wiki build` 명령으로 수행한다 —
> 기본은 background job 큐잉, `--wait`는 동기 실행. MCP에서는
> `curator_register_source`(L1) + `curator_build_source`(L2/L3)로 대응한다.

> **v0.2.1 성능 경로**: L2는 section-aware batch가 여러 개로 나뉘고 LLM client clone이
> 가능한 경우 batch 단위로 병렬 실행한다. L3는 embedding 기반 clustering을 먼저 시도하고,
> embedding 경로가 없을 때만 legacy LLM clustering plan으로 폴백한다.

---

## 5. Obsidian 플러그인 워크플로우

플러그인은 Obsidian 내에서 AI 어시스턴트로 동작하며, 선택적으로 Curator 백엔드와 연동합니다.

```text
Obsidian 플러그인 단독 사용:
  사용자 채팅 → LLM 직접 호출 (Antigravity/Claude/OpenAI)

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
     │ wiki curate 실행 (필요 시)
     ▼
L4 Exhibition 생성 → search_curator로 검색 가능
```

---

## 6. AI Agent(MCP) 워크플로우

Claude Code, Gemini CLI, Antigravity 같은 AI 에이전트는 MCP 서버를 통해 Curator에 접근합니다.

### MCP 서버 시작

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
     │    → 결과가 없으면 자동으로 wiki curate 실행
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
#    - ~/.gemini/settings.json
#    - ~/.gemini/antigravity/mcp_config.json
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
[Machine Layer]                                              ▼
  .curator/Collections/04_Exhibitions/ ◄─────── L4 EXH (workspace-scoped)
                    │
         ┌──────────┼──────────┐
         ▼          ▼          ▼
    wiki query  MCP Agent  Obsidian Plugin
   (CLI 검색)  (AI 에이전트) (채팅 사이드바)
```

---

## 관련 문서

- [플러그인 가이드](PLUGIN_GUIDE.md) — Obsidian 플러그인 기능 상세
- [MCP 사용 가이드](MCP_USER_GUIDE.md) — AI 에이전트 MCP 연결 설정
- [사용자 가이드](USER_GUIDE.md) — CLI 명령어 레퍼런스
- [시스템 철학](../philosophy/about.md) — Curator/Artist 메타포 배경

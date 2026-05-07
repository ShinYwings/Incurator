# 🛠 InCurator Contribution & Development Guide

이 가이드는 InCurator 프로젝트에 기여하려는 개발자들을 위한 문서입니다. 현재 프로젝트가 직면한 기술적 과제들과, 이를 안전하게 해결하기 위한 개발 환경(Testbed) 구축 방법을 설명합니다.

---

## 1. 현재 아키텍처: Curator as Compiler

InCurator는 개인 지식 베이스를 “검색 가능한 파일 묶음”이 아니라 검증 가능한 지식 DAG로 다룹니다. 처음 설계부터 이 DAG는 사람이 읽기 좋은 문서보다 **LLM이 안정적으로 읽고 추론하기 좋은 중간 표현(IR)**에 가깝게 만들어졌습니다. 현재 Curator는 source truth와 agent 대화를 L1-L4 DAG로 쌓고, `wiki sync`로 구조/논리 정합성을 되짚는 **compiler-inspired pipeline**입니다.

- **LLM-readable IR**: Context, Atom, Concept, Exhibition은 LLM이 읽고 추론하기 좋은 계층형 IR입니다. 각 layer는 사람이 보기 좋은 prose보다 안정적인 frontmatter, relation, provenance를 우선합니다.
- **Forward pass**: `wiki add`와 `wiki curate`는 source/workspace input을 L1-L4 DAG로 쌓아 올립니다.
- **Backward pass**: `wiki sync`는 생성된 DAG를 거꾸로 검증하며 structural gap, grounding gap, logical gap을 찾고 안전하게 수리 가능한 항목을 고칩니다.
- **Feedback signal**: 사람이 Context, Concept, Exhibition을 수정하거나 agent 대화에서 새로운 요구를 만들면, 그 차이가 sync와 재생성의 기준이 됩니다.

이 구조는 모델 출력이 흔들릴 수 있고, 지식 노드는 서로 의존하며, 사람이 수정한 내용은 다시 DAG 전체에 반영되어야 한다는 문제의식에서 발전해 왔습니다. 그래서 Curator는 단순 markdown 생성기가 아니라 다음 성질을 가진 compiler-inspired pipeline으로 설계되었습니다.

- **Stable IR**: layer schema, relation, provenance를 분리해 모델 출력 변동이 DAG 전체를 오염시키지 않게 합니다.
- **Sync as verification pass**: `wiki sync`는 type check처럼 구조 오류를 보고, grounding/logical gap을 역방향으로 확인합니다.
- **Affected subgraph rebuild**: 특정 L2/L3/L4가 바뀌면 전체를 다시 만들기보다 연결된 subgraph를 중심으로 재검증합니다.
- **Human feedback loop**: 사람이 고친 Context, Concept, Exhibition과 agent 대화 내용은 다음 sync/curate의 feedback signal이 됩니다.

## 2. 프로젝트 로드맵 및 현재의 한계 (Current Challenges)

핵심 challenge는 Curator를 더 실제 컴파일러에 가깝게 발전시키는 것입니다. 즉, LLM이 만든 지식 DAG를 단순 생성물이 아니라 검사, 최적화, 증분 재빌드, feedback 반영이 가능한 컴파일 산출물처럼 다루도록 고도화해야 합니다.

다음은 프로젝트를 진행하며 도출된 주요 향후 과제(Future Work)들입니다.

-   **`wiki add` 성능 최적화**: 현재 문서 등록 및 계층 생성(L1-L3) 속도가 매우 느립니다. 이 프로세스를 병렬화하거나 프롬프트를 최적화하여 문서 생성 속도를 혁신적으로 단축하는 것이 가장 시급한 과제입니다.
-   **소스 코드 지원 (Source Code Ingestion)**: 현재는 문서 위주의 지식 추출만 지원합니다. 소스 코드(Python, TS, C++ 등)를 직접 파싱하여 코드의 논리 구조, 함수 의존성, 핵심 알고리즘 등을 L2/L3 지식으로 추출하는 기능을 구현해야 합니다. 이는 개발자용 지식 베이스로서의 핵심 경쟁력이 될 것입니다.

### 🧠 Intelligence & Pipeline Quality
- **모델 벤치마크**: 작은 모델에서도 좋은 curation이 가능해야 하므로, layer별로 필요한 reasoning 수준과 fallback 전략을 측정해야 합니다.
- **프롬프트와 검증 분리**: 생성 프롬프트는 좋은 후보를 많이 만들고, sync 프롬프트는 논리 동등성, 모순, 병합 후보, grounding을 엄격하게 검증해야 합니다.
- **오케스트레이션 고도화**: L1-L4 생성, sync backprop, workspace curate, query session을 같은 정책 아래에서 조율하는 실행 모델이 필요합니다.

### 🏗 Architecture & State
- **통합 지식 엔진**: `qmd` 검색 인덱스와 Curator DB가 더 일관되게 협력해야 합니다. 검색 결과, DAG provenance, sync report가 서로 다른 진실을 말하면 안 됩니다.
- **동기화 친화적 상태 관리**: SQLite(`state.sqlite`)는 파일 잠금과 충돌에 취약합니다. 현재는 DB 파일을 sync에서 제외하는 방식을 권장하지만, 장기적으로는 더 sync-friendly한 state layer가 필요합니다.
- **재현 가능한 testbed 검증**: private fixture를 기반으로 `wiki add`, `wiki sync`, `wiki curate`, MCP 흐름을 반복 검증해야 합니다.

### 🛠 User Experience & Tooling
- **워크스페이스 설정 자동화**: `curate.yml` 작성과 agent rule provisioning을 더 쉽게 만들어야 합니다.
- **가시성 개선**: 사용자는 `wiki status`와 sync report만 보고도 어떤 layer가 clean/fixed/review_needed인지 이해할 수 있어야 합니다.
- **학습 곡선 완화**: compiler-like pipeline, forward/backward pass, layer status 같은 개념을 CLI와 문서에서 직관적으로 설명해야 합니다.

### 📂 Input Coverage
- **파서 지원 확대**: 이미지, PDF, 연구 자료, 전문 포맷 등 아직 파싱되지 않는 raw input을 안정적으로 L1 Context로 올릴 수 있어야 합니다.

---

## 3. 개발 및 검증 환경: Testbed 패턴

Testbed는 실제 지식 베이스(Vault)에 영향을 주지 않고 InCurator의 동작, 에이전트 성능, 큐레이션 로직을 검증하기 위해 사용하는 독립적이고 재현 가능한 환경입니다.

Testbed 소스에는 개인 노트, 워크스페이스 지시문, 연구 파일, 공개되지 않은 에이전트 대화가 포함될 수 있습니다. 이런 자료는 공개 commit에 포함하지 마세요. 

재현 가능한 개발 환경 구축에 대한 상세한 가이드와 템플릿 사용법은 [DEV_SCRIPTS_SPEC.md](file:///home/shin/Workspace/llm_wiki/docs/guides/DEV_SCRIPTS_SPEC.md)를 참고하십시오.

**테스트 베드 초기화 명령어:**
```bash
# 시나리오 목록 확인
wiki testbed list

# 특정 시나리오로 테스트 베드 구축 (기본: testbed_template)
wiki testbed init <scenario_name> --force
```

- **생성 스크립트 (`create_testbed.py`)**: 시나리오 자산에서 로컬 testbed vault를 재생성합니다.
- **Stage fixture**: notes, references, assets 등 testbed로 복사되는 원본 코퍼스입니다.
- **Dialogue scripts**: MCP/query/curation 동작을 반복 검증하는 대사/행동 스크립트입니다.
- **Fixture workspace rules**: private testbed workspace에 설치되는 dev 전용 agent rules입니다.
- **Master plan**: testbed 목적, source corpus, acceptance check를 설명하는 짧은 private 문서입니다.

### 핵심 철학: Private Stage Fixture
Testbed는 빈 폴더에서 시작하는 대신, 특정 도메인이나 문제 집합을 나타내는 정제된 소스 파일(L0) 세트인 **private stage fixture**에서 시작해야 합니다. fixture 자체는 Git에서 제외하고, 추상화된 testbed 패턴과 재사용 가능한 helper code만 공개할 수 있습니다.

#### 성공 기준
- **재현성 (Reproducible)**: 생성 스크립트를 실행할 때마다 매번 정확히 동일한 Vault 상태가 생성되어야 합니다.
- **격리성 (Isolated)**: `WIKI_ROOT` 환경 변수를 사용하여 메인 Vault와의 간섭을 완전히 차단합니다.
- **검증 가능성 (Verifiable)**: L1→L3 전환 및 소스 간 개념 병합(Concept Merging)을 테스트할 수 있을 만큼 충분한 복잡성을 포함해야 합니다.

> [!TIP]
> **실제 검증 사례 및 워크플로우**
> 개발 중에는 다음과 같은 private validation case로 시스템의 실용성을 검증할 수 있습니다:
> - **도메인 격리 및 병합 테스트**: 서로 연관된 개념 한 쌍(예: PDF 논문 + 해당 논문 분석 노트)과 전혀 다른 도메인의 지식 하나를 입력하여, 시스템이 연관 지식은 **Concept(L3)**으로 자연스럽게 묶고 무관한 지식은 명확히 격리하는지 확인합니다.
> - **워크스페이스 기반 실전 검증**: 실제 진행 중인 프로젝트의 워크스페이스를 Testbed에 추가하여 실전 환경을 시뮬레이션합니다. 예를 들어, 원본 데이터(Raw data)에서 특정 핵심 인사이트를 의도적으로 누락시킨 뒤, MCP 서버를 통해 해당 내용에 대해 질문합니다. 이때 시스템이 부족한 정보를 인지하고 Curator 업데이트를 통해 지식을 보완하거나 수정하는지 확인하여 파이프라인의 완성도를 검증했습니다.

---

## 4. 추상화된 디렉토리 구조

강력한 Testbed는 표준 Curator 구조를 따르되, `01_Workspaces`, `03_Notes`, `04_Resources` 디렉토리를 주요 "입력값"으로 집중 관리합니다.

```text
testbed/
├── 01_Workspaces/       # 에이전트별 규칙 및 워크스페이스 컨텍스트
│   └── <Workspace_Name>/
│       ├── .agents/      # 일반 코딩 에이전트용 규칙
│       └── .antigravity/ # Antigravity/Gemini 에이전트용 규칙
├── 02_Wiki/             # (선택 사항) 사람이 승인한 사전 지식
├── 03_Notes/             # 사람이 작성한 소스 진실 (가장 중요한 입력 데이터)
│   ├── Papers/          # 연구 논문에 대한 요약 및 노트
│   └── <Topic>/         # 도메인별 분류 (Math, Vision 등)
├── 04_Resources/         # 외부 참조 메타데이터 (예: Zotero 내보내기 파일)
├── 05_Assets/            # 이미지, PDF 및 바이너리 데이터
└── .curator/             # 시스템 내부 상태 (CLI를 통해 초기화됨)
    ├── Collections/      # 생성된 DAG (L1-L4)
    ├── config.yml        # Testbed 전용 LLM 및 경로 설정
    └── state.sqlite      # 출처(Provenance) 및 해시 추적 데이터베이스
```

---

## 5. 구현 워크플로우

Testbed를 생성할 때는 다음과 같은 자동화된 3단계 파이프라인을 따릅니다.

### 1단계: Stage 스캐폴딩 (Scaffolding)
private stage fixture 디렉토리를 Testbed 루트로 복사합니다. 이 fixture에는 테스트하려는 원본 `.md` 노트와 리소스 파일이 포함되어 있어야 합니다.

### 2단계: 시스템 초기화 (Initialization)
Testbed 디렉토리에 대해 `wiki init` 명령에 해당하는 작업을 수행합니다. 이를 통해 `.curator` 인프라를 구축하고 검색 인덱스를 설정합니다.

### 3단계: 에이전트 규칙 설치 (Agent Rule Installation)
`01_Workspaces` 디렉토리에 필요한 규칙 파일들(`AGENTS.md`, `CLAUDE.md` 등)을 배치합니다. 이를 통해 Testbed와 상호작용하는 에이전트들이 실제 운영 환경과 동일한 프로토콜을 따르도록 합니다.

---

## 6. 사용 및 검증

생성된 Testbed는 모든 명령 앞에 `WIKI_ROOT`를 붙여서 사용합니다.

```bash
# Testbed 상태 확인
WIKI_ROOT=testbed wiki status

# 시드된 노트를 기반으로 큐레이션 파이프라인 실행
WIKI_ROOT=testbed wiki add "03_Notes/**/*.md"
WIKI_ROOT=testbed wiki curate

# 특정 클레임 검증
WIKI_ROOT=testbed wiki query "fixture domain을 대표하는 질문을 입력하세요"
```

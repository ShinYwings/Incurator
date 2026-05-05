---
created: 2026-04-27T20:11
updated: 2026-05-06T00:00
---

# 🧠 Agentic Zettelkasten: Auto-Curating Workspace

파편화된 지식 자산의 홍수 속에서 막대한 토큰 낭비와 환각 없이 복잡한 프로젝트를 안전하게 수행하기 위해 만든 비용 효율적인 Multi-Agent DAG(Directed Acyclic Graph) 시스템입니다.

이 시스템은 지식을 연결하는 Zettelkasten 철학을 전문 큐레이션 아키텍처로 재구성했습니다. 수집된 외부 정보는 'Curator Engine'이 처리하며, 기계 친화적인 **4단계 전문 큐레이션 파이프라인(1단계: Context Summarization ➡️ 2단계: Atomization ➡️ 3단계: Concept Structuring ➡️ 4단계: Exhibition Staging)**을 거칩니다.

이 과정을 통해 정밀하게 '컴파일'된 지식 패키지만 강력한 추론 능력을 가진 'Execution Agent(Artist)'에게 주입됩니다. 최종적으로 인간과 에이전트의 협업을 통해 진정한 **Synthesis**를 이루고, 이를 시스템의 공식 지식(Wiki)으로 순환시키는 무한 지식 창출 루프를 형성합니다.

큐레이션 루프는 약간 훈련 과정처럼 동작합니다. `wiki add`와 `wiki curate`는 source knowledge를 DAG 위쪽으로 컴파일하는 forward pass이고, `wiki sync`는 backward verification pass입니다. 인간과 에이전트의 수정은 loss signal처럼 작동합니다. 생성된 노드가 근거에서 벗어나면 Curator는 그래프를 역추적하고, 생성된 구조를 안전하게 수리하며, 복구 가능한 L3/L4 노드를 다시 씁니다. 다만 이것은 실제 신경망 학습이 아니라 동작 비유입니다. 시스템은 불변 source truth를 덮어쓰지 않고, 애매한 수리는 인간 검토 대상으로 남깁니다.

## 이 시스템의 핵심 특징

### DAG-Based Knowledge Compiler

Curator는 노트를 평평한 검색 결과로만 저장하지 않습니다. Source material을 계층화된 evidence graph로 컴파일합니다.

```text
Source → L1 Context → L2 Atom → L3 Concept → L4 Exhibition
```

각 layer는 서로 다른 역할을 가집니다. L1은 source context를 보존하고, L2는 더 쪼개기 어려운 claims를 추출하며, L3는 관련 claims를 concepts로 엮고, L4는 agent가 바로 사용할 수 있는 task-ready knowledge package를 staging합니다.

### Integrity-Aware Curation

Curator는 한 번 생성하고 끝나는 generator가 아닙니다. 생성된 knowledge가 여전히 evidence로 역추적되는지 계속 확인합니다.

- `wiki add`와 `wiki curate`는 knowledge를 DAG 위로 forward compile합니다.
- `wiki sync`는 compiled graph를 source evidence 방향으로 backward trace합니다.
- 안전한 structural issue는 자동으로 수리합니다.
- 복구 가능한 generated-node gap은 L3/L4 page update로 이어질 수 있습니다.
- 애매한 case는 조용히 삭제하지 않고 review item으로 남깁니다.

### Workspace-Scoped Knowledge Staging

각 agent workspace는 `curate.yml`에 자신에게 필요한 knowledge scope를 선언할 수 있습니다. Curator는 그 specification을 기준으로 해당 workspace의 실제 task에 맞는 Exhibitions를 surface/stage합니다.

### Coverage-Preserving Concept Generation

Curator는 source Atoms가 L3 Concepts에 실제로 표현되었는지 확인합니다. clustering model이 관련 Atoms를 누락하면, Curator는 source/topic group에 대한 fallback Concept을 만듭니다. Retriever, Generator, BM25, Parametric Memory, Retrieval-Augmented Generation Atoms로 구성된 RAG cluster처럼 작지만 중요한 topic도 Concept으로 승격되어야 합니다.

## 👥 3 Core Entities (The Entities: Curator & Artist Metaphor)

우리 시스템은 **Cost Efficiency(FinOps)**와 추론 성능을 동시에 얻기 위해 각 주체의 역할과 사용 모델(Model Routing)을 엄격히 분리합니다.

| Entity | Metaphor (Role) | Architecture & Key Activities |
| :--- | :--- | :--- |
| **👤 Human** | Director | • `03_Notes` source knowledge의 생성자이자 소유자<br>• agent/curator가 제안한 지식을 검토하고 최종 의사결정(HITL)을 수행<br>• 대화를 통해 합의에 도달하고 최종 Wiki를 승인 |
| **⚙️ Curator** | Compiler | • `.curator/` hidden space에 상주하는 background engine<br>• knowledge graph(DAG) 유지보수와 데이터 전처리를 전담하여 토큰 소비 최적화<br>• L1 ➡️ L4 refinement pipeline 수행. 스스로 source truth를 창조하지 않음 |
| **🤖 Execution Agent (Agent)** | Artist | • `01_Workspaces/`에 상주하는 high-reasoning task executor<br>• 무거운 원본 검색 없이 curator가 staging한 exhibits를 기반으로 행동<br>• 코딩, 기획, 분석 등을 수행하고 합의된 지식을 `02_Wiki`로 승격 |

## 📂 Core Directory Structure & Data Permissions (Two-Track Architecture)

이 시스템은 machine-readable backend exhibition preparation space(`.curator`)와 human-readable domain knowledge space(`02_Wiki`)를 분리하는 two-track 디렉토리 구조를 가집니다.

```text
/
├── 00_System/               # 시스템 및 템플릿 관리(스크립트, prompt templates 등)
│
├── 01_Workspaces/           # 🎨 🤖 Artist(Agent) 거주지 / 지식 융합 및 프로젝트 실행 공간
│   └── {Project Name}/
│       ├── .agents/         # Agent control rules and persona settings
│       ├── Artifacts/       # 실험 코드, deliverables 등
│       ├── Concepts/        # 인간과 논의해 도출한 concepts. 합의 후 02_Wiki로 편입
│       ├── Papers/          # 글로벌 지식을 프로젝트 맥락에 맞춰 재해석하는 paper review sandbox
│       ├── curate.yml       # 🌟 [Knowledge Requirement Specification] Exhibition scope 결정
│       └── research_digest.md, todo_list.md 등
│
├── 02_Wiki/                 # 🏛️ 🤖 Agent & ⚙️ Curator-led official exhibition hall
│   └── 인간이 참조하기 편한 domain-based directory. 최종 Synthesis 결과 전시
│
├── 03_Notes/                # 👤 Human-centric source knowledge [PERM: Strict Read-Only]
│   └── 인간의 primary knowledge. 어떤 AI도 직접 수정하지 않음
│
├── 04_Resources/            # 📚 Immutable external knowledge [PERM: Strict Read-Only]
│
├── 06_Archives/             # 📦 Legacy knowledge [PERM: Read-Only]
│
└── .curator/                # ⚙️ Curator 전용 hidden space [PERM: Curator/Agent MCP Tool]
    ├── config.yml           # 프로젝트 환경 설정
    ├── state.sqlite         # hash registry 및 state tracking DB
    ├── overview.md & index.md # agent가 먼저 참조하는 routing tables
    ├── sync-report.json     # wiki status에 표시되는 latest integrity report
    └── Collections/         # 🧠 Curation 4-stage pipeline (L1~L4)
        ├── 01_Contexts/     # [Stage 1: Collection & Summarization]
        ├── 02_Atoms/        # [Stage 2: Selection & Atomization]
        ├── 03_Concepts/     # [Stage 3: Structuring & Value Addition]
        └── 04_Exhibitions/  # [Stage 4: Placement & Staging]
```

## ⚠️ Workflow and Operational Rules (Pipeline Rules)

### 1. The Curator's Bridge for Knowledge Exploration

- **목적:** 거대 모델(Agent)이 원문을 무의미하게 검색하면서 발생하는 토큰 낭비와 비용을 막습니다.
- **동작:** agent와 human은 새 query를 시작할 때 `03_Notes` 원본을 직접 뒤지지 않습니다. 대신 curator가 `.curator/`에 미리 배치한 **Exhibitions**를 먼저 탐색해 검증된 prior knowledge를 확보한 뒤 본격적인 reasoning을 시작합니다.
- **상세 메커니즘:** 각 workspace의 execution agent는 자신의 목표와 요구사항을 명시한 **Knowledge Requirement Specification(`curate.yml`)**을 가집니다. agent가 MCP server를 통해 curator에게 데이터를 요청하면, curator는 해당 spec에 맞는 지식을 선택해 Exhibition 형태로 제공합니다.

### 1.1 Integrity-Aware Curation

- **Forward pass:** `wiki add`는 source truth에서 L1 Contexts, L2 Atoms, L3 Concepts를 만듭니다. `wiki curate`는 workspace를 위한 L4 Exhibitions를 staging합니다.
- **Loss signal:** human 또는 agent의 수정, missing links, uncovered Atoms, logical gaps는 compiled DAG가 evidence와 어긋난 지점을 드러냅니다.
- **Backward pass:** `wiki sync`는 safe structural repair, logical verification, bounded generated-node repair를 실행합니다. 복구 가능한 L3/L4 nodes를 업데이트하고 affected downstream pages를 rebuild할 수 있습니다.
- **Boundary:** `wiki sync`는 `03_Notes`, `04_Resources`, `06_Archives`를 덮어쓰지 않습니다. 없는 Exhibition을 invent하지 않고, 애매한 knowledge를 fallback으로 삭제하지 않습니다.

### 2. Strong Human-AI Negotiation (HITL: Strong Negotiation)

- 시스템이 `03_Notes` 같은 source knowledge 내부의 logical contradictions 또는 errors를 발견하면, 원본을 임의 수정하지 않습니다. 즉시 작업을 멈추고 Director(Human)에게 이의를 제기해 논의를 시작합니다.
- **Principle of Immutability:** 인간이 승인하더라도 original note(`03_Notes`) 자체는 덮어쓰지 않습니다. 대신 `.curator/` 내부의 generated knowledge nodes(Atoms/Concepts)를 업데이트해 전체 시스템의 logical structure를 안전하게 바로잡습니다.

### 2.1 Sync Command

```bash
wiki sync          # default: safe repair + logical verification
wiki sync --no-fix # report-only
wiki sync --dry-run
```

`wiki status`는 Config, Sources, Collections, Pipeline Layer Status 다음에 latest sync health를 보여줍니다.

### 2.2 Coverage-Preserving Concept Generation

Concept generation은 source Atoms가 실제로 L3에 표현되었는지 확인합니다. clustering model이 관련 Atoms를 누락하면, Curator는 source/topic group에 대한 fallback Concept을 만들어 source를 조용히 complete 처리하지 않습니다. 예를 들어 Retriever, Generator, BM25, Parametric Memory, Retrieval-Augmented Generation 같은 RAG Atoms는 clustering model이 처음에 놓치더라도 RAG Concept으로 승격되어야 합니다.

### 3. Fusion of Knowledge and Ecosystem Circulation (Synthesis)

L4(Exhibitions) 단계의 exhibits는 query에 따라 실시간으로 새로 staging될 수 있습니다. 정제된 knowledge는 두 가지 경로를 통해 최종 official knowledge(`02_Wiki`)로 편입됩니다.

#### 🔄 Path A: Agent-Led Task Synthesis

- **Entity:** 🤖 Execution Agent(Artist) + 👤 Human(Director)
- **Process:** `01_Workspaces` 안에서 agent가 curator가 준비한 Exhibitions를 재료로 프로젝트 tasks를 수행합니다.
- **Result:** human과의 negotiation을 거쳐 완성된 insights와 deliverables를 agent가 `02_Wiki`에 기록합니다.

#### 💬 Path B: Conversational Promotion

- **Entity:** ⚙️ Curator + 👤 Human(Director)
- **Process:** human이 질문하면 curator는 자신이 구축한 Concept network(L3) 안에서 답합니다. 이후 human과 충분히 대화하며 ideas를 발전시킵니다.
- **Result:** 대화 중 도출된 내용이 좋은 concept이라고 판단되면 해당 내용을 `02_Wiki`로 official promotion합니다.

#### 🔁 The Infinite Loop

어떤 경로든 `02_Wiki`에 새로 staging된 official knowledge는 다시 background curator의 L1(Contexts) pipeline으로 유입되어 전체 knowledge ecosystem을 계속 확장합니다. 모든 변경은 `state.sqlite`에 기록되어 전체 DAG integrity를 유지합니다.

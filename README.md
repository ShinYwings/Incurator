---
created: 2026-04-27T20:11
updated: 2026-04-28T23:25
---

# 🧠 LLM Wiki 기반 Research Agent 파이프라인

이 워크스페이스는 **LLM Wiki** 기반의 **Local Distiller LLM(Raw File Ingestion)**, **QMD(Query Markup Documents)**, **Obsidian**, 그리고 **Research Agent**를 유기적으로 통합하여 자율적이고 신뢰성 높은 연구 파이프라인을 구축하는 공간입니다. 

에이전트(Agent)는 Zotero 등 외부 데이터베이스에 직접 접근하지 않고, 철저히 통제된 **Obsidian 내부 컨텍스트** 안에서만 탐색을 수행하여 환각(Hallucination)을 방지합니다. 외부 논문 등 새로운 정보가 필요할 때는 Zotero Integration을 통해 Obsidian 내부망(`02_Wiki` 또는 `03_Resources`)으로 안전하게 반입한 뒤 활용합니다.

---

## 📂 핵심 디렉토리 구조 및 역할

```text
/
├── 00_System/ (시스템 및 템플릿 관리)
|   ├── Scripts/ 
│   │   └── create_project.sh (표준 프로젝트 폴더 및 초기 템플릿 파일들을 자동 생성하는 스크립트)
│   └── Templates/ (수식 유도, 논문 요약, Zotero 포맷 등 반복 작업을 위한 템플릿 모음)
│
├── 01_Projects/ (마감 기한이 있는 프로젝트 - 🤖 에이전트 메인 워크스페이스)
│   └── {Project Name}/ (create_project.sh 로 자동 생성되는 표준 프로젝트 구조)
│       ├── .agents/ (에이전트 스킬 및 워크플로우 설정 - 심볼릭 링크)
│       ├── .antigravity/ (에이전트 제어 규칙 및 시스템 설정 - 심볼릭 링크)
│       ├── Artifacts/ (에이전트가 실험 과정에서 생성한 코드, 이미지, 중간 결과물 보관 공간)
│       ├── Concepts/ (사전 지식을 현재 프로젝트에 맞게 재구성한 개념 공간. 성숙되면 02_Wiki로 편입)
│       ├── Papers/ (사전 지식망에서 추출해 현재 프로젝트에서 직접 리뷰/사용하는 전용 논문 공간)
│       ├── Research Notes/ (프로젝트 진행 중 발생한 파편화된 데일리 리서치 기록)
│       ├── qmd.yml (🌟 에이전트가 어떤 Wiki와 Resource 맥락을 사전 지식으로 로드할지 결정하는 로더)
│       ├── methodology.md (엄밀한 기하학적/수학적 뼈대와 상호 동의된 파이프라인 설계가 기록되는 Ground Truth)
│       ├── related_works.md (선행 연구들을 분류하고 비판적 해석(Interpretation)을 기록하는 문헌 고찰)
│       ├── research_digest.md (Research Notes를 종합하여 기록하는 현재 시점의 연구 이해 상태 및 작업 가설)
│       └── todo_list.md (프로젝트 마일스톤 및 세부 태스크 트래킹)
│
├── 02_Wiki/ (LLM Wiki - 🤖 에이전트 자율 생성 지식 보관소)
|   └── Architecture/, Mathematics/ <-- 👤 사람 & 에이전트 공용 (도메인 디렉토리) 
│
├── 03_Resources/ (인간 중심 원천 지식 - 🛡️ Ground Truth / 🤖 Shallow 개입 허용)
│   ├── CS/, Math/, Vision/ (비전, 수학, CS 등 인간이 100% 이해하고 검증한 원자적 지식)
│   └── Papers/ (Zotero에서 가져온 원본 논문 및 요약)
│
├── .wiki/ (🤖 Distiller 전용 은닉 공간)
│   └── distilled/ (추출-합성 디렉토리) 
│       ├── Extracted/ (02_Wiki와 03_Resources에서 원자 단위로 쪼갠 파편 )
│       │   ├── Math_Logic/ (공식, 정리 추출물) 
│       │   └── Paper_Summaries/ (논문 핵심 요약) 
│       ├── Synthesized/ # 에이전트 전용으로 재구성된 지식 (Agent-Ready) 
│       │   └── Tech_Stacks/ (여러 파편을 결합한 기술 스택 정의서) 
│       └── Metadata/ ([03_Resources ↔ .wiki/distilled ↔ 02_Wiki] 연결 맵)
│
├── 04_Meta/ (인프라 및 시스템 에셋 관리)
│   └── Zotero Assets/ (Zotero와 연동하여 자동 추출된 이미지 및 스니펫 통합 보관소)
│
└── 05_Archives/ (종료된 프로젝트 및 레거시 데이터)
```

---

## ⚠️ 핵심 파이프라인 운영 규칙 (Agent Rules)

이 시스템의 무결성을 유지하기 위해 에이전트와 사용자가 반드시 준수해야 하는 운영 원칙입니다.

### 1. 01_Projects 내 폴더 및 에이전트 생성 규칙
- **파라미터 필수:** 프로젝트 생성 시 **프로젝트 이름**과 **Agent 설정 경로**(심볼릭 링크로 연결할 설정 파일들이 위치한 경로)가 파라미터로 전달되어야 합니다.
- **템플릿 활용:** 지정된 Template에 따라 프로젝트 폴더 구조 및 필요한 기본 `.md` 파일들이 자동 생성되어야 합니다.
- **독립적 구동 및 제약:** 에이전트는 오직 `01_Projects` 내 특정 프로젝트 폴더 안에서만 상주하며, 해당 폴더 내의 룰셋과 스킬에 완벽히 종속됩니다.
- **QMD 파이프라인 (qmd.yml):** 프로젝트 내의 `qmd.yml`은 에이전트가 워크플로우를 시작할 때 `02_Wiki`와 `03_Resources` 중 어떤 범위를 **사전 지식(Scope)**으로 삼을지 결정하는 핵심 설정 파일입니다.

### 2. 02_Wiki vs 03_Resources: 사전 지식 보관소의 역할 분담
- **`03_Resources` (Ground Truth):** 사람이 직접 검증한 핵심 원천 지식입니다. 에이전트는 이를 기반으로 RAG를 수행하여 환각을 차단합니다. 핵심 논리/수식 수정은 인간의 승인이 필수적이나, 오탈자 수정, 메타데이터 보강, 누락된 백링크 연결 등 지식망을 정비하는 **얕은 개입(Shallow Intervention)**은 에이전트 자율로 수행 가능합니다.
- **`02_Wiki` (Agent Knowledge):** 에이전트가 리서치 파이프라인을 수행하며 자율적으로 생산/요약한 지식이 누적되는 공간입니다.
	- **`.wiki/distilled/` (Data Ingestion)**
		- **Extracted (Distillation):** 핵심 개념을 원자 단위로 쪼개 `.wiki/distilled/Extracted/`에 저장합니다.
		- **Synthesized (Synthesis):** 파편들을 모아 에이전트가 이해하기 쉬운 구조로 합성해 `.wiki/distilled/Synthesized/`에 둡니다.
		- **Metadata (Wiki-Resource Mapping):** 03_Resources ↔ .wiki/distilled ↔ 02_Wiki 연결 맵

### 3. Agent의 탐색 및 지식 생성 파이프라인
사용자로부터 쿼리를 받으면, 에이전트는 먼저 **Distiller LLM**를 통해 사전 지식을 전처리하여 가져온 뒤 아래 상태에 따라 행동합니다:
- **상태 1 (관련 사전 지식이 있는 경우):** `Wiki`나 `Resource`에 정보가 존재하면 해당 정보를 가져와 컨텍스트와 파일 위치를 Output으로 반환하고, 이를 활용해 사용자의 태스크를 수행합니다.
- **상태 2 (새로운 사실을 알아내야 하는 경우):** 정보가 없다면 사용자의 검증 하에 다음 파이프라인을 수행합니다.
  - **Wiki 업데이트:** 에이전트는 `02_Wiki` 내에 새로운 폴더와 `.md` 파일을 스스로 생성해 내용을 업데이트합니다. (가능한 경우 `03_Resources` 지식으로 백링크(`[[...]]`)를 연결하는 것이 베스트입니다.)
  - **Zotero 연동 (외부 지식 획득):** 새로운 논문 등 외부 정보가 필요한 경우, 에이전트가 직접 외부망을 헤매는 대신 **Zotero Integration**을 호출해 필요한 자료를 Obsidian 내부망(`02_Wiki` 또는 `03_Resources`)으로 먼저 가져온 뒤 참조합니다.
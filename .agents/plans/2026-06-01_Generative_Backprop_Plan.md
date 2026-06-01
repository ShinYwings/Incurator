# Generative Backpropagation (wiki sync --backward) Implementation Plan

사용자님의 피드백을 반영하여, Generative Backprop 과정이 단일 LLM 호출이 아닌 **명시적인 Multi-Agent 아키텍처**로 동작하도록 설계를 고도화했습니다.

## User Review Required

> [!IMPORTANT]
> - 지시하신 대로 백프롭 과정 내부에 여러 Sub-agent 역할(성능/시간 평가, 워크스페이스 제어, 시스템 처리)을 배치하는 아키텍처로 계획을 수정했습니다.
> - 이 설계가 사용자님이 의도하신 "여러 sub agents를 두고 작업하는 구조"와 일치하는지 리뷰 부탁드립니다. 일치한다면 즉시 구현에 들어가겠습니다.

## Multi-Agent Backprop Architecture

Generative Backprop(`wiki sync --backward`)이 실행될 때, `sync.py` 내의 Orchestrator가 다음의 Sub-agent들을 호출하여 작업을 분담합니다.

### 1. Incurator System Sub-agents (시스템/추출 담당)
- **Insight Extractor Agent**:
  - 역할: 수동 편집된 L4 노드와 기존 하위 노드 간의 논리적 갭(VerificationGap)을 분석하여, 새롭게 주입된 "외부 인사이트(External Facts)"만을 정제된 텍스트로 추출합니다.
- **Atom Synthesizer Agent (L2)**:
  - 역할: 추출된 인사이트를 바탕으로 Incurator 스키마(`SCHEMA_v0.2.2.md`)에 완벽히 호환되는 새로운 L2 Atom 후보군을 생성합니다. 기존 `add_atom_from_insight` 로직을 이 에이전트 내로 캡슐화합니다.
- **Concept Clustering Agent (L3)**:
  - 역할: 새로 생성된 Atom을 기존의 L3 Concept에 병합(Merge)하거나 새로운 Concept으로 군집화합니다.

### 2. Workspace Sub-agent (워크스페이스/DAG 제어 담당)
- **DAG Controller Agent**:
  - 역할: 생성된 Atom과 Concept을 실제 파일 시스템(`.curator/Collections/`)에 쓰고, `dag_edges`와 라우팅 테이블(index, ledger 등)을 안전하게 업데이트합니다.
  - 특징: 무결성을 해치지 않도록 `sync.py`의 구조적 수리 로직과 연계하여 파일 I/O 및 스키마 검증을 전담합니다.

### 3. Time & Performance Evaluation Sub-agent (성능 평가 및 Critic 담당)
- **Evaluator / Critic Agent**:
  - 역할 1 (시간/성능): 각 시스템 Sub-agent(특히 LLM 호출)의 실행 시간(Latency)을 측정하고, 백프롭 처리가 너무 오래 걸릴 경우 Fallback(단순 모드)으로 전환하거나 경고를 발생시킵니다.
  - 역할 2 (논리 검증): Atom Synthesizer가 만든 L2 Atom이 실제로 L4의 논리적 갭을 메울 수 있는지(환각이 섞이지 않았는지)를 커밋 전에 교차 검증(Critic)합니다.

## Proposed Changes (Code Level)

### 1. `backend/src/curator/backprop_agents.py` [NEW FILE]
- 위에서 정의한 Sub-agent 클래스들을 구현합니다.
  - `TimePerformanceEvaluator`
  - `WorkspaceController`
  - `InsightExtractor`, `AtomSynthesizer`

### 2. `backend/src/curator/sync.py`
- `apply_generative_backprop` 함수가 단일 로직이 아니라, `backprop_agents.py`의 에이전트들을 오케스트레이션(Orchestration)하는 파이프라인으로 재작성됩니다.
  1. **Evaluator** 시작 (타이머 온)
  2. **Extractor**가 인사이트 추출
  3. **Synthesizer**가 Atom 생성
  4. **Evaluator**가 품질 검수 및 시간 로깅
  5. **Workspace Controller**가 DAG 업데이트 커밋 및 L3 클러스터링 트리거

### 3. `backend/src/curator/cli.py`
- `--backward` 플래그 실행 시 위 파이프라인을 호출하고, Evaluator Agent가 수집한 성능/시간 메트릭을 CLI 콘솔에 리포팅하여 사용자에게 투명하게 보여줍니다.

## Verification Plan
1. Testbed에서 L4 수정 후 `wiki sync --backward` 실행.
2. CLI 출력에 **각 Sub-agent의 동작 과정과 소요 시간(Performance metrics)**이 명확히 로깅되는지 확인.
3. 새로운 L2 Atom이 생성되고 논리적 갭이 해소되는지 검증.

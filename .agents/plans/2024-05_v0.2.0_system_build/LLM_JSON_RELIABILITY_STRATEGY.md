# LLM JSON Reliability & Extraction Strategy

이 문서는 Incurator 파이프라인에서 LLM이 구조화된 JSON 데이터를 추출할 때 발생하는 불안정성(Hallucination, 형식 파괴)을 해결하기 위한 현재의 아키텍처와 미래의 개선 방향을 기록한 문서입니다. 향후 AI 에이전트나 개발자가 파이프라인의 성공률을 끌어올리기 위해 참조해야 합니다.

## 1. 현재 아키텍처 (v0.2.1+)

현재 Incurator는 API 호출 비용과 시간을 절약하기 위해 여러 Atom을 한 번의 프롬프트로 추출하는 **Batch Extraction(한 번에 JSON 배열로 뽑아내는 방식)** 을 기본으로 사용합니다. (`ingest_orchestrator.py` 의 `run_l2_batch_extraction`)

하지만 가벼운 모델(예: `gemini-3.5-flash`)은 텍스트가 길어지면 JSON 배열 형식을 깨트리는 실수를 자주 합니다. 이를 방어하기 위해 다음과 같은 2단계 안전 장치가 구현되어 있습니다:

### 1-A. Self-Correction Loop (자가 수정 루프)
- 모델이 반환한 JSON 파싱 중 `JSONDecodeError`가 발생하면, 즉시 에러 메시지(`"Your previous response was invalid JSON. Error: {e}..."`)를 첨부하여 모델에게 재시도(최대 2회)를 요청합니다.
- 모델 스스로 실수를 피드백 받아 완벽한 JSON으로 고쳐내는 역할을 합니다.

### 1-B. Legacy Sequential Fallback (Sub-agent 병렬 추출 전환)
- 자가 수정(Self-Correction)까지 실패하거나 빈 배열(`[]`)을 반환하면, Batch 처리를 포기하고 즉시 기존의 **단일 Atom별 서브 에이전트 독립 생성 모드**로 우회(Fallback)합니다.
- 추출해야 할 각 Candidate마다 독립적인 LLM 프롬프트를 병렬로 실행하여 마크다운 텍스트를 직접 생성하므로, JSON 문법 제약에서 자유롭고 치명적인 데이터 누락(Skip)을 방지합니다.

---

## 2. 향후 아키텍처 개선 목표 (Next Steps)

현재의 Fallback 구조는 안전하지만, 레거시 모드로 진입하면 API 호출 횟수가 급증하는 단점이 있습니다. Batch Extraction의 근본적인 성공률을 극한으로 끌어올리기 위해 아래 2가지 기술적 해결책 도입을 우선적으로 검토해야 합니다.

### 2-1. Structured Outputs (JSON Schema API 강제) - **가장 권장됨**
- 최신 LLM API(OpenAI, Gemini 등)는 프롬프트 엔지니어링을 넘어서서 API 파라미터(예: `response_schema`) 수준에서 JSON 구조를 강제할 수 있습니다.
- 백엔드 클라이언트(`llm.py`)가 `agy`(Antigravity CLI) 또는 네이티브 SDK를 호출할 때 이 기능을 지원하도록 연동하면, 괄호를 빼먹거나 변수명을 틀리는 등의 문법 오류가 원천 차단됩니다. (성공률 거의 100%)

### 2-2. JSON Repair 라이브러리 적용
- LLM이 JSON을 망가뜨리는 패턴(주석 추가, 마지막 콤마(`,`) 잔존, 마크다운 펜스 꼬임 등)은 정규화되어 있습니다.
- 파이썬의 `json-repair` 같은 오픈소스 라이브러리를 도입하면, 문법이 망가진 JSON 텍스트를 복구하여 파싱 에러 자체를 대폭 줄일 수 있습니다. 

---
> **에이전트(AI)를 위한 중요 지침:** 
> 향후 "L2 Atom 추출 단계에서 에러가 발생한다"거나 "JSON 포맷이 자꾸 깨진다"는 이슈가 제기될 경우, 이 문서를 참조하여 `llm.py` 에 **Structured Outputs (Response Schema)** 를 연동하거나 **JSON Repair 라이브러리**를 도입하는 방향으로 시스템 설계를 제안하십시오.

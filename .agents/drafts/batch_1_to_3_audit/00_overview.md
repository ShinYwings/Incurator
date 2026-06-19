# Batch 1~3 심층 감사 총괄 개요 (Master Audit Overview)

## 1. 아키텍처 및 QA 총평 (Architectural & QA Verdict)

현재 Batch 1~3을 통틀어 구현된 시스템(Plan A ~ F)은 **수학적으로는 안전해 보이나, 논리적/구조적 모순으로 인해 실제 운영 환경에서 필연적으로 붕괴되는 상태(Structurally Fragile)** 입니다. 

수석 아키텍트 및 QA 엔지니어의 관점(Devil's Advocate)에서 이 시스템을 분석했을 때, 현재 파이프라인은 '환각 방지(Zero Hallucination)'라는 단일 목표에 매몰되어 **견고성(Robustness)과 재현율(Recall)을 완전히 희생**했습니다. 단위 테스트(Unit Test)와 단기 평가(Evaluation) 지표는 완벽해 보이지만, 이는 시스템이 오라클(Oracle)에 과적합되었기 때문이며, 실제 불규칙한 데이터를 주입할 경우 토큰 스래싱(Token Thrashing), 런타임 크래시, 그리고 상태 머신 누수(State Leak)가 연쇄적으로 발생합니다.

---

## 2. 구조적 모순 및 심층 분석 (Structural Contradictions)

**A. 배치 간의 철학적 충돌 (Batch 2 vs Batch 3)**
Batch 2(컴파일러)는 파편화된 그래프 생성을 허용합니다(엔티티 병합 금지). 그러나 Batch 3(서비스)는 예산(Budget)을 극도로 엄격하게 통제합니다. 이는 파편화된 노드를 탐색하기 위해 수많은 확장이 필요하지만, 시스템이 그 확장을 원천 차단하는 **자기 모순적(Self-Contradictory)** 설계입니다.

**B. QA 및 평가 지표의 기만성 (Deceptive Metrics)**
추적 변이(Trace Mutation) 버그(07번)로 인해 LLM 합성이 실패하면 검색 결과마저 지워집니다. 이로 인해 QA 러너는 "검색 모델이 못 찾았다"고 오진하게 되며, 엔지니어들은 Reranker나 임베딩 모델을 튜닝하는 헛수고를 반복하게 됩니다. 이는 지표(Metric) 자체가 오염된 최악의 상태입니다.

**C. 상태 머신 및 데이터 흐름의 붕괴 (State & Rank Obliteration)**
데이터가 레이어를 통과할 때마다 가장 중요한 컨텍스트가 소실됩니다. 정성껏 계산한 랭킹(Rank)이 `set()`과 `sorted()`의 무분별한 사용으로 인해 알파벳순으로 파괴되고(09번), CJK(한중일) 텍스트의 토큰을 영문 기준으로 하드코딩하여 계산함으로써(08번) LLM의 컨텍스트 한도를 무참히 초과시킵니다.

---

## 3. 감사 문서 인덱스 및 파일별 역할 (Audit Files Index)

총 10개의 심층 감사(Audit) 파일은 결함의 스코프에 따라 거시적(Macro) → 중시적(Meso) → 미시적(Micro) 단계로 분류되어 있습니다.

### [Macro] 시스템 및 방법론 결함 (Systemic Vulnerabilities)
이 파일들은 코드가 아니라 **설계 철학과 평가 방법론** 자체가 틀렸음을 증명합니다.
* **[01_systemic_oracle_overfitting.md](file:///Users/shin/shinywings/Incurator/.agents/drafts/batch_1_to_3_audit/01_systemic_oracle_overfitting.md)**
  * **역할:** Batch 1의 평가 체계(Failure Atlas)가 가지는 '합성 데이터 편향성'을 고발합니다. 시스템이 실제 사용자의 혼란스러운 노트가 아닌, 깨끗한 테스트 픽스처에만 과적합되고 있음을 분석합니다.
* **[02_systemic_graph_fragmentation.md](file:///Users/shin/shinywings/Incurator/.agents/drafts/batch_1_to_3_audit/02_systemic_graph_fragmentation.md)**
  * **역할:** Batch 2의 '자동 병합 금지' 정책이 야기하는 재현율(Recall) 0 문제와, 반대로 너무 느슨한 엣지가 유발하는 거대 연결 요소(Giant Component) 토큰 고갈 딜레마를 분석합니다.
* **[03_systemic_pipeline_fragility.md](file:///Users/shin/shinywings/Incurator/.agents/drafts/batch_1_to_3_audit/03_systemic_pipeline_fragility.md)**
  * **역할:** 마크다운 파서의 사소한 오류 하나가 Batch 3의 `ContextService`를 완전히 셧다운시키는 파이프라인의 극단적 취약성(Domino Effect)을 지적합니다.

### [Meso] 아키텍처 및 파이프라인 결함 (Architectural Flaws)
이 파일들은 `ContextService`와 모듈 간의 **계약(Contract) 위반 및 논리적 결함**을 다룹니다.
* **[04_arch_locator_coupling.md](file:///Users/shin/shinywings/Incurator/.agents/drafts/batch_1_to_3_audit/04_arch_locator_coupling.md)**
  * **역할:** 실제 DB 조인이 실패했음에도 ID 존재만으로 `source_supported`라는 거짓 상태를 반환하여 에이전트를 크래시로 몰고 가는 구조적 결함을 증명합니다.
* **[05_arch_budget_thrashing.md](file:///Users/shin/shinywings/Incurator/.agents/drafts/batch_1_to_3_audit/05_arch_budget_thrashing.md)**
  * **역할:** 예산 제한으로 확장이 거부된 항목을 시스템이 '누락(omitted)'으로 모호하게 처리하여, 에이전트가 무한 확장을 시도하게 만드는(Token Thrashing) UX/상태 설계의 결함을 파헤칩니다.
* **[06_arch_explore_bypass.md](file:///Users/shin/shinywings/Incurator/.agents/drafts/batch_1_to_3_audit/06_arch_explore_bypass.md)**
  * **역할:** `Explore` 라우트가 단일 진실 공급원인 `ContextService`를 몰래 우회하고 있는 아키텍처 위반(Contract Violation) 사태를 고발합니다.
* **[07_arch_trace_mutation.md](file:///Users/shin/shinywings/Incurator/.agents/drafts/batch_1_to_3_audit/07_arch_trace_mutation.md)**
  * **역할:** LLM 합성 실패 시 정상적인 검색 출처 데이터까지 덮어씌워 삭제해버리는, 평가 지표 오염의 주범(Trace Mutation)을 추적합니다.

### [Micro] 코드 단위 치명적 버그 (Micro-Level Bugs)
이 파일들은 특정 라인의 **수학적 오산, 메모리 누수, 자료구조 오용**을 정확히 짚어냅니다.
* **[08_micro_token_cjk_overflow.md](file:///Users/shin/shinywings/Incurator/.agents/drafts/batch_1_to_3_audit/08_micro_token_cjk_overflow.md)**
  * **역할:** `len(text)/4`라는 하드코딩된 토큰 계산식이 한/중/일(CJK) 텍스트 입력 시 어떻게 LLM 컨텍스트 초과(Overflow) 크래시를 유발하는지 수학적으로 증명합니다.
* **[09_micro_deterministic_reordering.md](file:///Users/shin/shinywings/Incurator/.agents/drafts/batch_1_to_3_audit/09_micro_deterministic_reordering.md)**
  * **역할:** BM25 및 Reranker가 정교하게 계산한 증거의 순위(Rank)를 `set`과 `sorted`의 무분별한 사용으로 알파벳순으로 뭉개버려, LLM의 어텐션(Attention)을 파괴하는 버그를 지적합니다.
* **[10_micro_expansion_state_leak.md](file:///Users/shin/shinywings/Incurator/.agents/drafts/batch_1_to_3_audit/10_micro_expansion_state_leak.md)**
  * **역할:** `context_expand`가 확장 후 상태를 DB에 올바르게 갱신하지 않아, 악의적(혹은 고장 난) 에이전트가 단일 노드를 무한대로 확장하여 DB와 토큰을 폭파시킬 수 있는 상태 누수(State Leak) 버그를 추적합니다.

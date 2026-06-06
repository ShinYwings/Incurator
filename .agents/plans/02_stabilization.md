# Core RAG & Knowledge Distillation Stabilization Plan

## Linked user_report Items
이 마일스톤이 해결하는 user_report 항목:
- **3**: qmd/검색 엔진 심층 분석 및 보완
- **4**: PDF 및 정제된 지식 내 수학 수식 누락 문제 해결
- **5**: 지식 정제용 LLM과 쿼리 확장(HyDE)용 LLM 설정 분리
- **6**: GraphRAG급 엔티티 통합, 노이즈 필터링 및 Vault Quota 아키텍처
- **7**: 전역적 사고를 위한 계층적 군집화 알고리즘 설계

## Context
현재 RAG 검색 엔진(Qwen3 Reranker + FTS5)과 지식 추출(Distillation) 파이프라인에서 발생하는 할루시네이션, 엣지(Edge) 유실, 사전 지식(Prior Knowledge) 맵핑 불안정성을 해결해야 합니다. Sync와 Annotation 개발에 앞서 기반을 닦는 최우선 과제입니다.

## Reference Plans (Must Read Before Implementation)
에이전트들은 다음 과거 아카이브 플랜들을 반드시 읽고, 기존 설계 의도와 RAG 구축 히스토리를 파악한 뒤 안정화에 돌입해야 합니다.
- `Git History (v0.3.2 search_internalization)`: (Qwen3 + FTS5 RAG 시스템 구축 히스토리)
- `Git History (2026-06-01_Generative_Backprop_Plan)`: (Generative Backprop 구조)
- `Git History (2026-06-01_Math_RAG_Backprop_Plan)`: (복잡한 수학/논리 백프롭 처리)

## Multi-Agent Debate Topics (For Codex & Claude)
1. **`schema_guardian`**: 
   - `search_documents`와 `knowledge_units` 간의 데이터 무결성을 검증하는 SQL 제약 조건을 어떻게 보완할 것인가?
2. **`source_pair_analyst`**: 
   - L3(Concepts) 및 L4(Synthesis) 레이어 생성 시, 원본 PDF Span(`source_spans`)으로의 역추적(Generative Backprop)이 끊어지는 버그의 원인은 무엇인가? 아카이브된 Backprop 플랜의 명세와 현재 구현체의 괴리를 어떻게 메울 것인가?
3. **`cli_regression_runner`**: 
   - `testbed` 스크립트를 통해 복잡한 RAG 질의 시 파이프라인 붕괴를 잡아낼 자동화 테스트를 어떻게 구성할 것인가?

## Implementation Skeleton
- `backend/src/curator/retrieval/*.py`: 과거 RAG 구축 플랜을 참조하여 Reranking 가중치 튜닝 및 하이브리드 서치 안정화.
- `backend/src/curator/pipeline/*.py`: L2->L3->L4 승격 로직의 프롬프트 및 유효성 검사 강화. (Generative Backprop 로직 정상화)
- `testbed`: `scripts/dev/`에 불안정성 및 Backprop 끊김 현상 재현을 위한 신규 시나리오 추가.

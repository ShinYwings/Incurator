# 00. Incurator v0.2.1 업데이트: 마스터플랜 및 아키텍처 명세서

> **상위 계약**: v0.2.1의 실제 스키마/동작 계약은
> `docs/spec/curator_schema/SCHEMA_v0.2.1.md`와
> `docs/spec/system_behavior/incurator_v0.2.1.md`이다. 이 디렉토리의 문서는
> 설계 근거와 구현 세부 계획이며, 코드와 테스트는 먼저 `docs/spec/` 계약을
> 만족해야 한다.

본 디렉토리(`v0.2.1_specs/`)는 Incurator 시스템을 단순한 Eager 추출기에서 벗어나, **피드백을 수용하고 역전파(Backprop)를 수행하는 "정제된 지식 컴파일러"**로 고도화하기 위한 v0.2.1 업데이트의 초정밀 기술 명세서 모음입니다.

단일 문서에 담기엔 이 시스템의 아키텍처적 깊이(DOM 파싱, Autoencoder 매핑, 백그라운드 오케스트레이션, 역전파 동기화 등)가 방대하므로, 도메인별로 완전히 분리된 문서를 통해 어떠한 디테일도 요약되지 않은 날것 그대로의 설계 철학과 구현 방안을 명시합니다.

## 명세서 구조 (Directory Index)

1. **`01_Architecture_Analysis.md`**: 기존 동기식 Eager DAG 시스템의 근본적 병목과, Ask Gemini 메커니즘을 융합한 "투트랙(Two-Track) 하이브리드 시스템" 간의 딥 다이브(Deep Dive) 비교 분석.
2. **`02_Frontend_MCP_Bridge.md`**: 옵시디언 플러그인(`externalPdfView.ts`) 내의 PDF.js Native API 연동, DOM/A11y Tree 기반 구조적 주입(Structural Injection), 그리고 완벽하게 파싱된 상태의 MCP Payload 전송 규격 명세.
3. **`03_Autoencoder_DAG_Compiler.md`**: (업데이트됨) 전체 문서 분석의 완전성을 유지하면서도 추출 품질을 극대화하기 위한 **"ToC-Guided Full Extraction"**. Attention Routing을 활용한 Encoder(L1→L3) / Decoder(L3→L4) 압축 및 Skip-Connection(Grounding 보존) 설계.
4. **`04_Background_Orchestration.md`**: 클라이언트 블로킹 문제를 원천 차단하기 위한 파이썬 백그라운드 데몬, `state.sqlite` 기반의 큐잉, 그리고 `l2_status='pending'` 비동기 폴링 메커니즘.
5. **`05_Sync_Backprop.md`**: 지식 컴파일러의 핵심인 역전파 로직. 사용자 및 에이전트의 모순 지적(Loss Signal)을 바탕으로 `wiki sync`가 어떻게 에러를 역추적(Backward Pass)하고 특정 서브그래프만 증분 재빌드(Incremental Rebuild)하는지에 대한 알고리즘.
6. **`06_Infra_and_Migration.md`**: `shared/models.json`을 통한 설정 중앙화, 그리고 기존 `gemini-cli` 의존성을 벗어난 `agy` (Antigravity CLI) 마이그레이션 전략.
7. **`07_Exhibition_Session_Model.md`**: MCP `curator_query` 호출 시 Exhibition을 즉석에서 생성하는 Query-time 동적 합성 모델. Pre-baked → Query-generated → Promoted 3-Tier Lifecycle, 워크스페이스 단위 캐싱, 채팅 세션과 Exhibition의 관계(세션은 트리거, Exhibition은 워크스페이스 자산), 승격(Promotion) 플로우 명세.
8. **`08_Performance_SubAgent_Architecture.md`**: ingest 파이프라인이 느린 근본 원인 전수조사(LLM 호출 횟수, 순차 L3/L4, thread-safety 버그), Google Ask 사이드바와의 설계 철학 비교, L2/L3/L4 서브에이전트 + 오케스트레이터 병렬 아키텍처 설계, SQLite 동시성 안전성 보장 전략, wiki sync hash 기반 incremental 검증, v0.2.1 구현 우선순위.
9. **`09_Visualization_and_Observability.md`**: 백그라운드 IngestWorker 진행률 / 지식 정제 DAG 구조 / 에이전트 쿼리 경로, 3개 관찰 경계를 커버하는 시각화 아키텍처. dag_edges SQLite 테이블, `.curator/dashboard.md` 자동 갱신, Obsidian Canvas 기반 빌드 트레이스, curator_query() trace 필드 + Plugin "Sources & Trace" 패널.

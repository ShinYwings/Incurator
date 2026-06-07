---
name: arxiv_cross_reference
description: 특정 수식이나 기법을 최신 SOTA 기하학적 제약 조건과 교차 검증 및 비교
---
# ArXiv Cross-Reference Method (Master Pipeline Step 2 연동)

이 스킬은 `.agents/workflows/research_pipeline.md`의 **[Step 2. Universal Verification]** 단계 수행 시 보조적으로 활성화되며, 특정 수식이나 기법이 최신 SOTA 기하학적 제약 조건과 부합하는지 교차 검증합니다.

## 검증 방법
1. **Top-Tier 문헌 검색**: 주어진 수식/기법과 관련된 최신 3D Vision 논문들을 ArXiv 검색 도구 등으로 탐색할 때, **반드시 탑티어 컨퍼런스(CVPR, ICCV, ECCV, SIGGRAPH 등) 및 우수 저널(TPAMI, IJCV 등)에 게재/게재 예정인 논문만을 엄격히 필터링**하여 레퍼런스로 사용합니다. 출처가 불분명한 단순 ArXiv 프리프린트는 교차 검증의 팩트 체크 근거로 채택하지 않습니다.
2. **기하학적 차별점 분석**: 제안된 기법이 최신 논문들의 $Orthogonality$ 제약 조건 등 기하학적 특징과 어떻게 다른지 비판적으로 분석합니다.
3. **표 정리**: 비교 분석 결과를 SOTA 논문들과 대조하는 명확한 표 형태로 정리하여 응답의 가독성과 학술적 가치를 높입니다.

---
name: cuda_taylor_analyzer
description: CUDA 커널 코드 내 수식의 Taylor 전개 근사 차수 수치적 분석
---
# CUDA Taylor Analyzer Method (Master Pipeline Step 2 연동)

이 스킬은 `.agents/workflows/research_pipeline.md`의 **[Step 2. Universal Verification]** 단계 수행 시 활성화되며, 제공된 레포지토리의 실제 $CUDA$ 커널 코드에서 이론적 수식이 어떻게 근사(Approximation)되어 구현되었는지 분석합니다. 특히 3D Gaussian Splatting(3DGS) 류의 고도로 최적화된 렌더링 파이프라인 분석에 특화되어 있습니다.

## 검증 방법 (Gaussian Splatting 특화)
1. **커널 코드 추출**: 3DGS 레포지토리의 `forward.cu` 혹은 `backward.cu` 등 핵심 C/CUDA 커널을 추출합니다.
2. **Jacobian 및 공분산 수식 매핑**: 커널 내의 행렬 곱 연산이나 타원 투영(Elliptical Projection) 연산을 논문의 이론적 수식($Taylor$ 1차 전개, EWA Splatting 등)과 정확히 매핑하여 대응시킵니다.
3. **근사치 규명(Discrepancy Check)**: 코드가 연산 최적화를 위해 우아한 수학적 룰(예: 부분 공간 사영)을 어느 수준까지 꼼수(Taylor 전개 절단, LPF 상수화 등)로 근사시켰는지 파악하고 그 오차 범위를 수치적으로 보고합니다.

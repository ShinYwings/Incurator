---
name: linear_algebra_verifier
description: 변환 행렬의 행렬식(Determinant)과 특이점(Singularity) 분석 가이드라인
---
# Linear Algebra Verifier Method (Master Pipeline Step 2 연동)

이 스킬은 `.agents/workflows/research_pipeline.md`의 **[Step 2. Universal Verification]** 단계에서 활성화되며, 3D Vision 논문이나 코드에서 제시된 변환 행렬(Transformation Matrix)의 기하학적 정보 손실 유무를 수치적으로 엄밀히 검증하기 위한 방법론입니다.

## 검증 방법 (Methodology)
1. **행렬 추출**: 제시된 변환 행렬 수식을 파악합니다.
2. **수치 검증 (필요시)**: Python 코드 인터프리터(`numpy`, `sympy` 등)를 자율적으로 활용하여 행렬식(`Determinant`)을 계산할 수 있습니다.
3. **결과 해석**:
   - $det(A) = 0$ 인 경우, 변환 시 정보 손실(Singularity)이 발생함을 지적합니다.
   - 정보의 손실 여부와 기하학적 의미를 엄밀하게 기술합니다.

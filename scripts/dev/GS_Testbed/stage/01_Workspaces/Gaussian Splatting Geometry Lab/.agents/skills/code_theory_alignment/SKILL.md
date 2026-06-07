---
name: code_theory_alignment
description: 논문 상의 Jacobian 수식과 연산 그래프(Autograd 등) 간의 정적 분석 가이드라인
---
# Code-Theory Alignment Method (Master Pipeline Step 2 연동)

이 스킬은 `.agents/workflows/research_pipeline.md`의 **[Step 2. Universal Verification]** 단계에서 활성화되며, 논문의 이론적 수식(특히 Jacobian 등 미분/역전파 수식)과 실제 딥러닝 구현체(예: PyTorch `autograd`, CUDA Kernel)가 일치하는지 정적 분석하는 방법론입니다.

## 검증 방법 (Methodology)
1. **수식 분석**: 논문에서 제시하는 주요 연산의 변환식과 Jacobian을 수식으로 정리합니다.
2. **코드 분석 (필요시)**: 사용자가 제공한 코드 Snippet에서 해당 연산이 어떻게 근사(Approximate)되거나 구현되었는지 추적합니다. (예: Custom CUDA Kernel의 backprop 식)
3. **Discrepancy 체크**:
   - 이론적인 기댓값과 실제 연산 그래프 간의 오차 요소나 생략된 항(term)이 있는지 지적합니다.

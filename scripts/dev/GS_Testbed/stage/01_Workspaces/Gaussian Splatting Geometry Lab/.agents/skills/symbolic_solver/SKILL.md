---
name: symbolic_solver
description: SymPy 등을 활용한 수식 대수적 항등식 및 Rank Condition 계산 스킬
---
# Symbolic Solver Method (Master Pipeline Step 2 연동)

이 스킬은 `.agents/workflows/research_pipeline.md`의 **[Step 2. Universal Verification]** 단계 수행 시 활성화되어, SymPy 등의 기호 연산 라이브러리를 활용해 챗봇이 유도한 수식의 엄밀성을 대수적으로 계산 및 검증합니다.

## 검증 방법
1. **수식 모델링**: 챗봇이 유도하거나 분석 중인 수학적 모델을 기호(Symbolic) 형태로 변환합니다.
2. **항등식 검증**: 제안된 수식이 모든 조건에서 성립하는 대수적 항등식인지 수치/기호적으로 검증합니다.
3. **조건부 성립 분석**: 특정 조건(예: $Rank$ $Condition$, $Determinant \neq 0$)에서만 성립하는 경우, 해당 제약 조건을 명확히 산출하여 답변에 포함시킵니다.

---
created: 2026-04-27T21:57
updated: 2026-04-27T21:57
---
# Optimal Transport (OT) 개념 사전

  

## 1. Unbalanced Optimal Transport (UOT)

- **출처**: [26] MCMC 3DGS, [16] Light UOT 등 OT 문헌들

- **정의**: 전통적인 최적 수송(Balanced OT)은 소스(Source)와 타겟(Target) 간의 총 질량(Mass)이 정확히 동일해야 함 $\sum w_i^{src} = \sum w_j^{tgt}$. 반면 UOT는 질량의 소멸(Destruction)과 생성(Creation)에 비용(Cost, 예: Kullback-Leibler 발산)을 매겨, 질량이 보존되지 않는 시스템을 최적화.

- **연구 연결점**: 프레임이 바뀔 때 객체가 나타나거나 사라지는 현상, 그리고 TSP/3DGS에서 Gaussian이 Split/Merge/Remove 되는 현상은 모두 "질량이 보존되지 않는 분포 변환" (UOT의 Birth-Death Process)으로 통합 해석 가능.

  

## 2. 2-Wasserstein Distance ($W_2$)

- **정의**: 두 확률 분포 간에 질량을 옮기는 데 드는 '최소 일(Work)'을 측정하는 거리. 단위 거리당 코스트가 유클리디안 거리의 최고($L_2$)일 때 $W_2$라 칭함.

- **연구 연결점**: TSP의 Hard boundary 추정을 Soft-assignment로 치환할 때 사용하는 핵심 메트릭. 프레임 간 2D GMM의 궤적을 연결하는 코스트 함수.

  

## 3. Bures Metric (가우시안 쌍의 Closed-form $W_2$)

- **출처**: Optimal Transport for Applied Mathematicians

- **정의**: 두 다변량 정규 확률 분포 $\mathcal{N}_1(\mu_1, \Sigma_1)$과 $\mathcal{N}_2(\mu_2, \Sigma_2)$ 사이의 $W_2$ 거리는 닫힌 해(closed-form)가 존재한다:

$$ W_2^2(\mathcal{N}_1, \mathcal{N}_2) = \|\mu_1 - \mu_2\|^2 + \text{tr}\Big(\Sigma_1 + \Sigma_2 - 2\big(\Sigma_1^{1/2}\Sigma_2\Sigma_1^{1/2}\big)^{1/2}\Big) $$

- **연구 연결점**: 전체 GMM($N$개의 가우시안 합) 간의 $W_2$는 닫힌 해가 없음. 따라서 각 가우시안 컴포넌트(Component)를 하나의 "점"으로 취급하여 개별 컴포넌트 간의 Bures Metric 코스트 행렬을 만든 뒤 이산(Discrete) OT 문제로 풀어 근사(Approximation)한다. 이때 픽셀 색상 거리를 확장 특징 공간으로 추가.
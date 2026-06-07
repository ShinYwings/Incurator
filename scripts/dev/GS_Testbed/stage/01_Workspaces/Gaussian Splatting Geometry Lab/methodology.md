---
created: 2026-04-27T21:15
updated: 2026-04-27T21:51
---
# Methodology: End-to-End 3D Gaussian Splatting from Video

*Status: [선행 연구 리뷰 및 기하학적 뼈대 구축 중]*

> [!IMPORTANT]

> 이 문서는 오직 엄밀한 수학적/기하학적 코드 검토 및 **상호 동의(Mutual Agreement)**가 완료된 이론만을 수록합니다.

  

## 1. Global Mathematical Notations

본 문서 및 파이프라인 전체에서 전역적으로 일관되게 사용되는 수학적 기호(Global Notation Consistency)입니다.

- $\Sigma_{3D}$: 3D 가우시안 공분산 행렬 (반드시 $Positive$ $Semi-definite$ 성질 유지)

- $\Sigma_{2D}$: 2D 이미지 평면에 투영된 가우시안 공분산

- $\mathbf{T}_{cw} \in SE(3)$: 월드 좌표계에서 카메라 좌표계로의 강체 변환(Rigid Transformation) 행렬

- $\mathfrak{se}(3)$: 시간 $t$에 따른 에고모션(Ego-motion) 최적화 증분을 위한 리 대수(Lie Algebra) 도메인

- $J$: 핀홀 카메라 투영에 대한 1차 야코비안(Jacobian) 선형 근사 행렬

- $\mathbf{W}$: World-to-Camera 회전 매트릭스 부분 ($\mathbf{R} \in SO(3)$)

  

---

  

## 2. 수식 구체화 및 검증 (Process & Formulation)

  

### 2.0 연구 가능성에 대한 문헌적 껼데(Evidence from Literature)

우리의 접근법은 세 가지 선행 연구와 직접 연결된다:

- **RAIN-GS `[Ref: RAIN-GS]`**: 크고(Large) 희소한(Sparse) 가우시안 초기화일수록 최적화의 수용 공간(Basin of Attraction)이 넘어져 학습에 유리함을 증명. 2D 이미지에서 Lifting한 초기 GS가 크고 Sparse함을 정당화하는 선례.

- **Superpixel-guided Compact 3DGS `[Ref: Superpixel-guided Sampling]`**: 2D Superpixel 구조가 3D GS 샘플링/초기화의 유효한 기하학적 매핑으로 작동함을 증명. TSP 궤적 기반 2D Gaussian에서 Lifting하는 접근의 직접적 선례.

- **On-the-fly NVS `[Ref: On-the-fly NVS]`**: 비디오 스트림을 순차적으로 받아 실시간 GS 구축이 가능함을 증명. 프레임 단위 점진적 Lifting 파이프라인의 실허 가능성(Feasibility)을 지지.

  

### 2.1 2D Image as 2D Gaussian Mixture (GMM) `[Ref: Temporal Superpixels (TSP)]`

이미지 $I(x, y)$를 2D 가우시안들의 합(Mixture)으로 근사. 이 표현의 **잘지 레퍼런스(Direct Reference)는 TSP**로, TSP에서는 각 Superpixel을 독립적인 **가우시안 확률 상태(State)**로 모델링하고, 프레임 간 시간적 일관성을 **가우시안 프로세스(Gaussian Process)**로 만족시킬 수 있다고 주장한다:

$$ I = \sum_{i=1}^N c_i \mathcal{N}(\mu_{2D, i}, \Sigma_{2D, i}) $$

  

- **시간적 일관성 및 2D 트래킹**: 연속된 비디오 프레임 $t, t+1$ 사이에서 각 Superpixel 상태 $\mathcal{N}(\mu_{2D}(t), \Sigma_{2D}(t))$의 이동은 **SEA RAFT**를 통해 추출된 Dense Optical Flow 기반으로 궤적이 추적된다. (단, 이 2D Flow는 공간적/기하학적 일관성이 없으므로, 향후 Lifting 단계에서 Epipolar Geometry 및 MVG 제약을 통해 기하학적 3D 궤적으로 교정된다).

- **3DGS와의 차이**: 3DGS`[Ref: 3DGS]`는 3D 스플래팅 렌더링의 레퍼런스이며, 2D GMM 표현의 기원럼이 아니다.

- **분할(Splitting) 전략**: 각 $\Sigma_{2D}$는 Positive Semi-definite 성질를 유지해야 함.

  

### 2.2 Keyframe-based Two-View Matching

연속된 모든 프레임을 Two-view로 취급하면 베이스라인(Baseline) 너비가 너무 좁아 삼각측량 시 기하학적 깊이 오차가 발산하는 **Parallax failure**가 발생한다. 이를 방지하기 위해 **On-the-fly NVS `[Ref: On-the-fly NVS]`**의 철학을 철저히 따른다. On-the-fly NVS는 카메라 포즈의 거리(Translation/Rotation) 변화량이나 새롭게 관측된 영역의 비율을 추적하다가, 일정 임계치를 넘었을 때만 프레임을 **Keyframe**으로 등록하여 충분한 Baseline을 확보한다. 본 파이프라인 역시 인접한 Keyframe 쌍 사이에서만 Two-view 정합 및 3D Lifting을 수행하도록 강제한다.

  

### 2.3 3D Lifting & The Alpha-Compositing Paradox

두 뷰 사이의 2D 가우시안 $\Sigma_1, \Sigma_2$를 단순히 **Homography $H$**로 연결하여 3D Disk를 복원하려는 시도는 **Surface Rendering의 Alpha Compositing 원칙과 정면으로 충돌**할 위험이 크다.

  

- **비판적 쟁점**: 2DGS의 렌더링은 단일 평면의 투영이 아니라, 깊이 순서로 정렬된 수많은 가우시안들의 **알파 블렌딩(Accumulation)** 결과물이다.

- **Homography의 한계**: 만약 특정 2D 가우시안 영역이 여러 개의 3D 가우시안이 겹쳐서 만들어진 결과라면, 이를 단일 평면 유도 호모그래피로 Lifting하는 순간 기하학적 왜곡이 발생한다.

- **수정된 전략**:

1. **Initialization**: $L_\infty$ Norm이나 Angle Error Triangulation을 통해 '개별' 가우시안의 3D 중심점 및 대략적인 법선을 잡는다. (이때 호모그래피는 단지 '단일 평면' 가정하의 약한 초기값으로만 사용).

2. **Verification (Differentiable Rendering Phase)**: 초기화된 GS들을 실제로 렌더링하여 얻은 픽셀 값과 타겟 이미지 사이의 **Photometric Loss**를 통해 Lifting 결과를 사후 검증(Verification)하고 미세 조정한다.

3. 즉, Lifting 주체는 기하학적 Homography 등식이 아니라, **Alpha Compositing을 인지하는 Differentiable Rasterizer**가 되어야 한다.

  

### 2.4 Unbalanced Optimal Transport (UOT)

*Status: [탐색적 브레인스토밍 단계 — 아직 정립되지 않음]*

  

이전 프레임의 3D 가우시안(Memory/Prior)과 2D 관측 데이터 사이의 코스트를 정의한다.

  

**코스트 함수 설계 (탐색 중)**:

- **컨포넌트 레벨 이산(Discrete) $W_2$**: 각 가우시안 컨포넌트를 "질량 $w_i$를 가진 점"으로 보고, 확장된 특징 공간 $(μ, \Sigma, c)$에서의 쌍별 Bures metric + 색상 거리를 ground cost로 사용하는 이산 OT 문제로 치환.

- 개별 가우시안 쌍의 $W_2$: $W_2^2(\mathcal{N}_1, \mathcal{N}_2) = \|\mu_1 - \mu_2\|^2 + \text{tr}(\Sigma_1 + \Sigma_2 - 2(\Sigma_1^{1/2}\Sigma_2\Sigma_1^{1/2})^{1/2})$ (Bures metric, closed-form)

- GMM 전체의 연속 $W_2$는 closed-form이 없으므로, 컨포넌트 레벨의 이산 OT로 근사

- **확장된 특징 공간**: 위치 $\mu$ + 공분산 $\Sigma$ + 픽셀 컨러 $c$를 결합하여 기하학적 이동 + 색상 변화를 동시에 코스트로 잡는다.

  

**이미지 레벨 보조 로스 (탐색 중)**:

- $W_2$ 코스트(컨포넌트 레벨) + **SSIM**(이미지 레벨)을 병용하는 방안 검토 중.

- $W_2$: 가우시안 간 대응의 질 (기하학적 정합)

- SSIM: 렌더링 결과 전체의 구조적 유사도 (최종 품질 검증)

- ⚠️ 두 로스의 gradient 방향이 충돌할 가능성 있음 → 가중치 $\lambda$ 스케줄링 또는 커리큘럼 필요할 수 있음 (future ablation)

  

### 2.5 정적 씬 및 Ego-Motion 최적화

카메라 이동만을 고려하는 Static Scene 가정 하에, 시간 $t$에 따른 3D 가우시안의 절대적 좌표계는 불변하며, 모든 에러(Discrepancy)는 시점 변화 $\mathbf{T}_{cw}(t) \in SE(3)$ 에 기인한다고 최적화:

$$ \min_{\mathbf{T}_{cw}} \sum \mathcal{W}_2(\mathcal{N}_{2D}^{obs}, \text{Proj}(\mathcal{N}_{3D}^{prior}, \mathbf{T}_{cw})) $$

  

### 2.6 확률론적 동역학 관점: SDE Formulation `[Ref: Score-based Generative Modeling]`

에고모션과 3D 가우시안 형상 변위는 다음과 같은 확률미분방정식(SDE)으로 통합된다.

$$ d\mathbf{X}_t = \underbrace{f(\mathbf{X}_t, \mathbf{T}_{cw}(t))}_{\text{Drift (Flow Matching)}} dt + \underbrace{G(\mathbf{X}_t)}_{\text{Diffusion (MCMC Noise)}} d\mathbf{W}_t $$

  

---

  

## 3. 기하학적 체크포인트 (Geometric Checkpoints)

1. **$Rank$ 퇴화 방어**: $\Sigma_{3D}$ 역투영 단계에서 텐서 구조 유지 증명.

2. **리 대수 최적화**: $\mathbf{T}_{cw}$ 증분이 반드시 $\mathfrak{se}(3)$ 상에서 이루어지는지 여부 (`cuda_taylor_analyzer` 활용 예정).
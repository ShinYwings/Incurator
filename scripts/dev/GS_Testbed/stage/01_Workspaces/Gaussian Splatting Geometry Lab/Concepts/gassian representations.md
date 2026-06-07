---
created: 2026-04-27T21:57
updated: 2026-04-27T21:57
---
# Gaussian Representations 개념 사전

  

## 1. 2D Gaussian State (TSP 기원)

- **출처**: [4] Temporal Superpixels (TSP)

- **정의**: 이미지 평면의 픽셀들을 그룹화(Superpixel)한 뒤, 이를 단순한 스플랫이 아닌 독립적인 확률 상태(Probability State) $\mathcal{N}(\mu_{2D}, \Sigma_{2D})$ 로 모델링.

- **연구 연결점**: 3DGS는 렌더리를 위한 구조체일 뿐이며, 비디오 입력을 2D GMM으로 모델링한다는 발상은 TSP가 기원이다. 단 TSP 구현체는 시간적 연속성을 Optical Flow로 퉁쳤기에 이 비어있는 GP 연속성 부분을 UOT로 치환하는 것이 핵심 아이디어.

  

## 2. Low-Pass Filter (LPF) Singularity Hack (2DGS 꼼수)

- **출처**: 2DGS 공식 코드 구현체 (surfel_splatting)

- **정의**: 2DGS 논문은 "볼륨 렌더링 대신 완전한 $Rank=2$ 2차원 표면(디스크)을 렌더링한다"($\Sigma_{3D}$ 의 한 고유값이 0)고 주장. 그러나 디스크를 측면(Edge-on 부근)에서 보면 사영 시 2D 공분산 행렬 $\Sigma_{2D}$ 가 선분($Rank=1$)에 가까워져, 렌더링 식에서 역행렬 $\Sigma_{2D}^{-1}$ 계산 시 $NaN$으로 폭발(Singularity)함.

- **문제점**: 이를 피하기 위해 코드 단에서 공분산 행렬 대각 성분에 강제로 `+0.3f` 정도의 큰 LPF 상수를 더함. 이는 "완벽한 $Rank=2$ 2D 표면"이라는 기하학적 가정을 스스로 깨고 강제로 "Rank=3 인 3D 타원체"처럼 렌더링하는 치명적 수학적 모순(Logical Leap)임.

- **연구 연결점**: 2DGS의 수학적 허점을 지적할 가장 강력한 코드-이론 괴리(Code-theory gap) 사례.

  

## 3. Adaptive Density Control vs Split/Merge/Remove

- **정의**:

- **3DGS ADC**: Gradient를 기반으로 $\Sigma_{3D}$의 고유값 방향을 따라 3D 가우시안을 쪼개거나(Split, Clone), 불투명도가 낮으면 지움(Prune).

- **TSP Policy**: 2D 영역에서 분할/결합 규칙을 통해 Superpixel 단위로 나누거다 합침.

- **연구 연결점**: 두 기법 모두 GMM의 구성 요소를 조작하는 Heuristic이며, 본 연구에서는 이를 UOT의 Birth-Death Process(질량 생성/소멸 보상) 모델로 수학적 통합(high-level framing)하여 보다 글로벌하게 최적화할 계획.
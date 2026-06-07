---
created: 2026-04-27T21:16
updated: 2026-04-27T21:51
---
# Related Work (문헌 고찰)

  

이 문서는 `methodology.md`에서 도출된 파이프라인과 관련된 선행 연구들을 범주별로 분류하고,

연구자와의 대화 속 기하학적 추론 규칙에 입각한 각 논문의 **비판적 해석(Interpretation)**을 기록합니다.

(목표: 논문 초안 작성을 위한 Literature Review 섹션 기반 자료)

  

---

  

## 1. 3D Representation & Rendering (3D/2D GS)

**주요 참고 논문**:

- `[1]` *3D Gaussian Splatting for Real-Time Radiance Field Rendering (Kerbl et al., 2023)*

- `[2]` *2D Gaussian Splatting for Geometrically Accurate Radiance Fields (Huang et al., 2024)*

- `[3]` *RAIN-GS: Relaxing Accurate Initialization Constraint for 3D Gaussian Splatting*

  

### 1.1. Gaussian Splatting 특징 (3DGS vs 2DGS) `[1, 2, 3]`

- **핵심 해석**: 기존 3DGS`[1]`는 SfM Point Cloud 초기화에 전적으로 의존한다. 깊이 추정이 부정확할 시 Pose 에러와 Camera Extrinsic이 결합되어(Coupled Error) 큰 기하학적 왜곡을 낳는다.

- **RAIN-GS의 가장 중요한 둥찰**: RAIN-GS`[3]`는 완화된 초기화를 제안하면서, **크고(Large) 희소한(Sparse) 가우시안으로 시작할수록 학습 시 더 넓은 수용 공간(Basin of Attraction)을 확보하여 최적화에 유리하다**는 것을 실험적으로 증명하였다. 이는 2D 이미지에서 Lifting한 초기 GS의 shape이 크고 Sparse하여도 학습의 관점에서 배제할 필요가 없음을 공식적으로 지지하는 **중요한 선례(Precedent)**이다.

- **방법론(`methodology.md`) 연결점**: 2DGS`[2]`의 판(Disk) 구조를 차용하여 공분산에 $Rank=2$ 제약을 주입해 역투영 모호성을 타개해야 한다. Lifting 초기 단계에서는 RAIN-GS의 논리에 근거하여 크고 Sparse한 GS를 의도적으로 생성하는 전략이 타당하다.

  

---

  

## 2. Temporal Consistency & Tracking (비디오 연속성)

**주요 참고 논문**:

- `[4]` *Temporal Superpixels (TSP)*

- `[5]` *Segment Anything Model 2 (SAM 2, Ravi et al., 2024)*

  

### 2.1. TSP의 코드-이론 괴리(Code-Theory Gap) 및 SAM2 기각 `[4, 5]`

- **TSP의 핵심 해석**: TSP`[4]`는 논문에서 각 Superpixel을 가우시안 확률 상태(State)로 보고, 프레임 간 시간적 일관성을 **가우시안 프로세스(Gaussian Process)**로 모델링한다고 주장한다. 그러나 코드에는 GP가 **구현되어 있으나 실제 효과가 없으며**, `reestimated_flow = false`로 설정해도 결과에 차이가 없다. 실제로는 Optical Flow가 시간 연속성을 담당하고 있다.

- **TSP의 split/merge/remove/switch 전략**: 이 전략은 3DGS의 Adaptive Density Control(ADC: Split/Clone/Prune)과 구조적으로 유사하며, UOT의 Birth-Death Process(질량 생성/소멸)와도 연결된다. 단, 2D 영역 분할(TSP)과 3D 공분산 기반 분할(3DGS)의 **수학적 등가성은 추가 증명이 필요**한 열린 문제이다.

- **우리 방법론에서의 의미**: TSP의 "가우시안 상태(State) 표현"이라는 아이디어 자체는 유효하지만, 연속성 보장 메커니즘(GP)이 구현되지 않은 상태로 남아있다. **이 미완성된 영역을 우리의 UOT/SDE 프레임워크로 채우는 것이 바로 Contribution 지점**이다.

- **SAM2 기각**: SAM2`[5]`는 의미론적 분할에 강하나 2D 픽셀 도메인$(u,v)$에서만 작동하여 3D 공간 기하를 전혀 인지하지 못하므로 트래킹 알고리즘은 기각. 3D 가우시안들 자체가 씬의 기하학적 상태를 누적 저장하는 메모리 뱅크 역할.

- **방법론(`methodology.md`) 연결점**: 2D 도메인의 흐름은 TSP 궤적을 관측치로 삼아 UOT 최적 수송의 코스트로 활용하되, 연속성 보장은 TSP가 수식으로만 제안하고 구현하지 못한 GP 대신 우리의 SDE/UOT 기반 동역학으로 치환한다.

  

---

  

## 3. Pose Optimization & Structure Alignment (SLAM & 최적화)

**주요 참고 논문**:

- `[6]` *ORB-SLAM3: An Accurate Open-Source Library (Campos et al., 2021)*

- `[7]` *Generalized Procrustes Analysis (GPA) / Procrustean Markov Process*

- `[8]` *ICP, Generalized-ICP (G-ICP), Normal Distributions Transform (NDT)*

- `[27]` *RegGS: Unposed Sparse Views GS with 3DGS Registration (ICCV 2025)*

- `[44]` *CoMapFree 3DGS*

  

### 3.1. Camera Pose Estimator & Alignment `[6, 7, 8, 27, 44]`

- **핵심 해석**: Pose-Free 환경에서 Gauge Freedom에 빠질 위험이 크므로 ORB-SLAM3`[6]` 식의 고전적 Feature 제약이 GS 단에서 재해석되어야 한다.

- **CF-GS`[44]` 활용**: 첫 번째 프레임의 로컬 3D 공간을 **월드 공간으로 간주**하여 metric depth 추론 없이 서로 다른 프레임의 유클리드 공간 불일치 문제를 해결. 단, **scale ambiguity**가 남아있으며 이에 대한 논리적 대응이 필요.

- **RegGS`[27]` 활용**: 프레임 간 GS 정합(Registration)을 위해 RegGS 방식을 레퍼런스로 삼음. RegGS는 sparse view + unposed 설정이나, 우리는 sequential video이므로 부드러운 변화 + 작은 baseline이라는 더 강한 제약을 활용할 수 있어 오히려 유리한 점을 강점으로 삼아야 함.

- **방법론(`methodology.md`) 연결점**: 초기 정렬에 GPA`[7]` 구조를 활용하고, 에고모션을 $Wasserstein$ 거리 기반 코스트로 묶어 추적 수송한다. ICP/G-ICP`[8]`와 본 방법론 간의 등가 증명이 향후 논문에 필수적으로 실려야 한다.

  

---

  

## 4. 연구 가능성 지지 증거 (Supporting Evidence)

**주요 참고 논문**:

- `[RAIN-GS]` *RAIN-GS: Relaxing Accurate Initialization Constraint for 3D Gaussian Splatting*

- `[SP-GS]` *Superpixel-guided Sampling for Compact 3D Gaussian Splatting*

- `[OTF-NVS]` *On-the-fly NVS*

  

### 4.1. 세 논문이 증명하는 것을 종합하면: 우리 연구가 가능하다

| 논문 | 증명하는 것 | 우리 연구와의 연결 |

|---|---|---|

| RAIN-GS | Large & Sparse GS가 최적화에 유리 | Lifting 시 크고 Sparse한 GS 생성 전략의 이론적 근거 |

| Superpixel-guided Compact 3DGS | 2D Superpixel 구조 → 3D GS 초기화 유효 | 2D TSP 기반 Gaussian에서 Lifting하는 접근의 직접적 선례 |

| On-the-fly NVS | 비디오 스트리밍 실시간 GS 구축 가능 | 점진적 Lifting 파이프라인의 Feasibility 증명 |

  

- **핵심 해석**: 세 논문은 각각 서로 다른 서브프로블러금을 해결하였으나, 세 가지를 **동시에 성립**하는 통합 파이프라인은 아직 나오지 않았다.

- **통합적 UOT 관점**: 나아가, TSP의 split/merge/remove/switch, 3DGS의 Adaptive Density Control(Split/Clone/Prune), UOT의 Birth-Death Process(질량 생성/소멸)는 하이레벨에서 보면 모두 **"질량이 보존되지 않는 분포 변환" = UOT 문제의 인스턴스**로 바라볼 수 있다. (수학적 등가 주장이 아닌 추상적 통합 관점임에 유의)

- **우리 방법론이 제공하는 새로운 것**: heuristic 기반 밀도 제어를 UOT로 재해석하면, 코스트 함수에 기하학적 제약(Epipolar 등)을 직접 인코딩하여 기존 heuristic이 놓치는 글로벌 최적 질량 재배치를 보장할 수 있다.
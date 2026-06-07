---
created: 2026-04-27T21:29
updated: 2026-04-28T05:16
---
# Research Digest (연구 종합 사고 정리)

  

> [!IMPORTANT]

> 이 문서는 날짜별 `Research Notes/`에 파편화된 기하학적 통찰들을 **종합(Synthesis)**하여, 시스템이 새로운 분석을 수행할 때 반드시 참고해야 하는 **현재 시점의 연구 이해 상태(Living Research Memo)**입니다.

> `methodology.md`에 승격되기 전의 **작업 가설(Working Hypothesis)** 및 **확정된 비판적 분석(Confirmed Critique)**을 기록합니다.

  

---

  

## 1. 파이프라인 구조 (현재 확정)

  

```

[Input 정의]

가상 이미지(Blender 등) 또는 카메라 파라미터(K)가 주어진 RGB 이미지 파일.

렌즈 왜곡(Lens Distortion)은 고려하지 않음 (Undistorted 입력 가정).

  

[Phase 0: Anchor — 최소 2프레임 입력 필수]

Frame 1, 2 → TSP → 2D GMM 쌍 추출

→ Direct Conic Triangulation으로 초기 3D Disk Lifting

→ Frame 1의 로컬 3D 공간 = World Space (CF-GS [44] 철학)

  

[Phase 1: Bootstrap (Frame 3~6)]

→ 키프레임 쌍의 Conic 대응으로 E 추정 (K는 주어짐)

→ Direct Conic Triangulation: 중심점(μ) 삼각측량 + Apparent Contour(Σ)로 법선·스케일 복원

→ 월드 좌표에서 직접 탄생

  

[Phase 2: Steady-state (Frame 7~)]

→ MAP Loss:

Prior = 기존 3D GS 렌더링 (σ_p: 모델 성숙 시 감소)

Likelihood = 새로 Lifted GS 렌더링 (σ_l: 고정, 힌트 역할)

→ Prior 텀 → 포즈 + 기존 GS 정제

→ Likelihood 텀 → 새 GS만 정제 (gradient detach로 분리)

→ UOT: 기존 3D GS ↔ 새 2D 관측 매칭/업데이트/탄생/소멸

```

  

### 핵심 설계 원칙

- **Depth 추정 모델 미사용** → Mono 입력 불가, 반드시 2프레임 이상

- **CF-GS 앵커링** → RegGS식 병합(Merge) 불필요. 모든 GS가 월드 좌표에서 직접 탄생

- **TSP 렌더링은 Loss에 사용하지 않음** → TSP는 2D Disk 파라미터 추출용으로만 사용. Loss의 Likelihood는 Lifted GS의 렌더링

  

---

  

## 2. 확정된 비판적 분석 (Confirmed Critiques)

  

### 2.1 2DGS의 Ray Space 상실 및 LPF 꼼수 문제

- **Ray Space 상실**: 3DGS `[1]`의 Jacobian $J$는 모든 가우시안을 동일한 **Ray space**에서 평가하여 기하학적 무결성을 보장하나, 2DGS`[2]`는 독립적 Homography만 사용하여 통일된 Ray space가 부재함. 결과적으로 3D에서 교차하지 않는 Disk도 2D 타일 오버랩으로 컴포지팅에 참여하는 구조적 결함 발생.

- **LPF의 이율배반성**: 2DGS는 Edge-on Singularity를 막기 위해 대각 성분에 상수($+0.3f$)를 더하는 Low-Pass Filter를 사용함. 이는 "2차원 표면(Rank-2) 렌더링"이라는 수학적 전제를 스스로 파괴하고 억지로 얇은 부피(Rank-3)를 부여하는 자가당착적 꼼수임.

  

### 2.2 수학적 동치성: 3DGS 투영 = MVG Dual Quadric 투영

- 3D 가우시안 투영식 $\Sigma_{2D} = J \mathbf{W} \Sigma_{3D} \mathbf{W}^T J^T$는 사영 기하학의 **쌍대 이차곡면(Dual Quadric) 투영 공식 $\mathbf{C}^* = \mathbf{P} \mathbf{Q}^* \mathbf{P}^T$와 수학적으로 완벽히 동치(Isomorphic)**임.

- 이에 따라 $\Sigma_{3D}$ Lifting 문제는 다중 뷰 기하의 Quadric 복원 문제로 정밀하게 치환 가능함.

  

### 2.3 Cheirality 및 기하학적 보존

- **Cheirality**: $\lambda > 0$ 제약은 Perspective Division의 분모=0에 의한 **Jacobian Rank 퇴화**를 막는 필수 방어선. Lifting 최적화 시 $Z > \epsilon$ Barrier 필수.

- **Conic 보존**: 사영 투영은 선형이므로 타원 형태는 보존됨. 왜곡의 주범은 투영 자체가 아닌 비선형 렌즈 왜곡임.

---

  

## 3. 탐색 중인 가설 (Working Hypotheses)

  

### 3.1 Direct Conic Triangulation Closed-form [TODO: 수식 유도 필요]

- 두 뷰의 대응 2D Gaussian ($\mu_1, \Sigma_1$), ($\mu_2, \Sigma_2$) + 카메라 행렬 $P_1, P_2$로부터:

- Step A: $\mu_{3D}$ = 중심점 삼각측량 (Angular Error `[13]`)

- Step B: $\Sigma_{2D}^{(i)} \propto P_i Q^* P_i^T$ 관계로 Rank-2 Disk $Q^*$의 법선 $\mathbf{n}$ 및 스케일 $(\lambda_1, \lambda_2)$ 복원

- Over-determined (6 제약 vs 4 DOF) → closed-form 해 존재 예상

- **미해결**: 실제 수식 유도 (`symbolic_solver` 스킬로 검증 필요)

- **위험 요인**: Baseline이 작으면 법선 추정 수치 불안정

  

### 3.2 Apparent Contour를 F 추정의 Constraint로 활용 가능성 [TODO: 탐구 필요]

- Steiner Conic Transfer ($\mathbf{S}^* = \mathbf{F}\mathbf{C}^*\mathbf{F}^T$)와는 다른 접근

- Conic 대응을 직접 Lagrangian의 constraint로 사용하여 $F$ 또는 $E$ 추정

- 현 단계에서는 $K$를 주어진 것으로 가정

  

---

  

## 4. 기각된 대안 및 대응 전략 (Rejected Alternatives & Defense)

  

### 4.1 Unscented Transform (UT) 기각

- UT의 잠재적 활용처는 Homography의 Grazing angle(경사 입사) 케이스에서 발생하는 비선형성 전파임. 그러나 바로 그 케이스에서 2DGS는 이미 LPF 꼼수로 공분산을 오염시키므로, UT를 적용해봤자 잘못 설계된 렌더링 위에 얹히는 셈. 더 근본적으로, 우리 파이프라인은 Homography 대신 **Direct Conic Triangulation + MAP Loss 사후 검증**을 채택하므로 UT가 삽입될 자리 자체가 없음.

  

### 4.2 SAM2 트래킹 기각

- 2D 픽셀 기반 트래킹은 3D 공간 기하(에피폴라 등)를 인지하지 못하므로 기각. 대신 GS 자체가 씬의 기하를 저장하는 '메모리 뱅크' 역할을 수행하도록 함.

  

### 4.3 Scale Ambiguity 대응 (Devil's Advocate)

- 첫 프레임을 월드로 고정할 때 발생하는 절대 스케일 미지수는 본 연구의 스코프 밖(Future Work)으로 규정하여 방어. 본 연구의 목적은 '상대적 스케일에서의 기하학적 연속성' 증명임.
---
created: 2026-04-27T21:52
updated: 2026-04-27T21:52
---
# 3D Vision Research Action Items (TODOs)

  

## 1. Ablation Studies (절제 연구 의무화)

> `methodology.md`에 등재된 핵심 모듈/제약에 대한 성능 입증 실험 (Ablation Study Mandate)

- *(아직 기획된 Ablation Study 없음. 향후 파이프라인 컴포넌트 추가 시 자동 추출 예정)*

  

## 2. Research Note 후속 과제 (Action Items)

> 일일 토의 베이스캠프에서 파생된 [수식 증명 / 논문 리서치 / 코드 실험] 과제 (Action Item Extraction)

### 🎯 1차 마일스톤 (지금 집중)

- [ ] **[2026-03-23 발췌] GS Prior (메모리 뱅크) 파이프라인 설계**: SAM2의 2D 픽셀 트래킹을 기각하고, 3D 가우시안 집합 자체를 다음 프레임 Lifting을 안내할 Prior 삼기 위한 파이프라인 전체 구체화

- [ ] **TSP → 2D GMM**: TSP 출력의 각 Superpixel에서 $(\mu_{2D}, \Sigma_{2D}, c)$ 추출 구현

- [ ] **Two-view 3D Lifting**: 두 프레임의 대응 2D 가우시안 쌍에 MVG Dual Conic 연산($\mathbf{C}^* = \mathbf{P}\mathbf{Q}^*\mathbf{P}^T$)으로 $\Sigma_{3D}$ (Rank=2 Disk) 복원

- [ ] **2DGS 렌더링 품질 확인**: Lifted GS를 2DGS 방식으로 렌더링하여 SSIM/PSNR 수준 확인

  

### ⏸️ Future Work (Parked)

- [ ] **[FUTURE]**: MCMC/SGLD 기반 샘플링 방식으로 명시적 불확실성 추정 — 1차 마일스톤 확인 후 재검토

- [ ] **[FUTURE]**: $W_2$ + SSIM 병용시 gradient 충돌 $\lambda$ 스케줄링 ablation
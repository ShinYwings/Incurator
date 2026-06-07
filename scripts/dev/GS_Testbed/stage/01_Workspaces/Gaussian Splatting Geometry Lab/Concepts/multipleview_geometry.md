---
created: 2026-04-27T21:57
updated: 2026-04-28T19:32
---
# Multiple View Geometry (MVG) 개념 사전

  

## 1. Dual Conic (쌍대 원뿔곡선) & Dual Quadric (쌍대 이차곡면)

- **출처**: Multiple View Geometry in Computer Vision (Hartley & Zisserman)

- **정의**:

- 일버적인 Conic(원뿔곡선) $\mathbf{C}$는 점(Point)들의 궤적으로 정의되며 $\mathbf{x}^T \mathbf{C} \mathbf{x} = 0$을 만족.

- **Dual Conic** $\mathbf{C}^*$는 선(Line)들의 궤적(Envelope)으로 정의되며 $\mathbf{l}^T \mathbf{C}^* \mathbf{l} = 0$을 만족. $\mathbf{C}^* = \mathbf{C}^{-1}$ (가역일 때).

- **직관**: 점이 아니라 외곽선(접선)들의 집합으로 도형을 정의하는 기하학적 방식.

- **연구 연결점 (핵심)**: 2D Gaussian Splatting의 2D 공분산 행렬 $\Sigma_{2D}$는 정확히 MVG의 **Dual Conic $\mathbf{C}^*$**과 수학적으로 동치(Isomorphic)이다.

  

## 2. 투영(Projection) 관계식

- **출처**: MVG Quadric Projection Theorem

- **정의**: 3D 공간의 Dual Quadric $\mathbf{Q}^*$가 카메라 카메라 행렬 $\mathbf{P}$에 의해 2D 이미지 평면으로 투영되어 만들어지는 Dual Conic $\mathbf{C}^*$는 행렬 곱으로 닫힌 해를 가짐.

$$ \mathbf{C}^* = \mathbf{P} \mathbf{Q}^* \mathbf{P}^T $$

- **연구 연결점**: 2DGS 논문의 투영 식 $\Sigma_{2D} = J \mathbf{W} \Sigma_{3D} \mathbf{W}^T J^T$ 과 완벽히 동일하다. 즉, 2DGS는 사영 기하학의 Quadric 투영을 선형 근사 렌더링에 차용한 것이다.

  

## 3. 대수적 삼각측량 (Algebraic Triangulation of Conics)

- **정의**: 한 뷰에서 관측된 2D 도형(Conic) 하나만으로는 원래의 3D 도형(Quadric)의 스케일과 깊이를 알 수 없음 (Scale Ambiguity / Null Space). 무수히 많은 원뿔 기둥(Cone) 형태의 가능성이 존재.

## 4. Fundamental Matrix & Apparent Contours

- **정의 (Fundamental Matrix)**: 두 이미지의 대응점 $\mathbf{x}, \mathbf{x}'$ 간의 에피폴라 기하를 나타내는 행렬. $\mathbf{x}'^T \mathbf{F} \mathbf{x} = 0$.

- **정의 (Apparent Contour)**: 3D 곡면(Quadric $\mathbf{Q}^*$)을 투영할 때 시각적으로 맺히는 윤곽선(2D Conic $\mathbf{C}^*$).

- **수학적 엄밀성**: 카메라 중심 $\mathbf{C}$에서 Quadric으로 쏜 모든 시선(Ray) 중 Quadric 표면에 '접하는(Tangent)' 시선들의 집합이 **Contour Generator** 공간 곡선(3D)을 형성하며, 이는 카메라 중심의 측면에서의 극평면(Polar plane)과 Quadric의 교선이다. 이 곡선이 이미지 평면에 사영된 것이 곧 Apparent Contour.

- 2D Gaussian의 공분산 타원 $\Sigma_{2D}$는 바로 이 3D 공간상의 밀도 분포(혹은 2D Disk) 표면에 접하는 시선들의 다발이 만들어낸 극평면 단면의 Apparent Contour이다.

- **정의 (Steiner Conic / Conic Intersection)**: 두 Conic의 교차점이나 공통 접선을 분석할 때 나타나는 기하학적 궤적.

- **연구 연결점**: 단순히 Dual Conic 투영 행렬식($\mathbf{C}^* = \mathbf{P}\mathbf{Q}^*\mathbf{P}^T$)의 대수적 풀이(Algebraic solver)에만 의존하면 노이즈에 취약함. 대신 $\mu_{2D}$ 중심점들로 $\mathbf{F}$를 강건하게 추정한 뒤, 두 뷰의 Apparent Contour(2D 공분산 타원)와 에피폴라 기하 곡선(Steiner conic 등)을 활용해 Triangulation을 기하학적으로 제약(Constrain)하면 복원 안정성이 크게 향상됨.
  

## 5. $L_\infty$ Norm Optimization

- **출처**: Multiple-View Geometry under the $L_\infty$ Norm `[Ref: 39]`

- **특징**: 전통적인 $L_2$ 재투영 에러는 아웃라이어에 취약하고 Non-convex한 특성을 가짐. 반면 $L_\infty$ 노름(최대 수직 거리)을 최소화하면 문제가 Convex(SOCP 등)하게 변환되어 전역 최적해(Global Optimum)를 찾는 데 유리함.

- **연구 연결점**: 카메라 포즈 정보가 매우 불안정한 초기 단계에서 아웃라이어(잘못된 TSP 매칭)에 강건한 초기 3D 위치를 추정하는 데 활용 가능.

  

## 6. Angular Error based Triangulation (ICCV 2019)

- **출처**: Closed-Form Optimal Two-View Triangulation Based on Angular Errors `[Ref: 13]`

- **특징**: 픽셀 평면상의 거리가 아닌, 카메라 원점(Center)에서의 '시선 벡터(Ray direction)' 간의 사잇각(Angle)을 최소화하는 방식.

- **연구 연결점**: 2DGS의 Rank-2 Disk는 시선 방향에 매우 민감함. 특히 비디오 스트림에서 Depth가 바뀔 때, 픽셀 좌표 오차보다 각도 오차를 줄이는 것이 3D Disk의 법선(Normal) 방향을 훨씬 물리적으로 타당하게(Optimal) 결정함.
# Incurator Master Roadmap

이 문서는 Incurator 아키텍처 대공사를 위한 마스터 로드맵입니다. 규모가 방대하므로 단계를 엄격히 분리하여 구현합니다. `AGENTS.md`의 다중 에이전트(Multi-Agent) 롤에 맞춰 Claude Code 및 Codex 에이전트들이 아래의 서브 플랜들을 치밀한 구현 명세서(Implementation Spec) 수준으로 토론하고 완성해야 합니다.

**Global Priority Rule**: 각 단계를 시작하기 전 반드시 `.agents/user_report.md`를 먼저 확인하고, 미해결 항목부터 처리하세요. 이 로드맵은 구현 순서를 정의하는 스켈레톤입니다. 실제 구현 시에는 `PLAN_TEMPLATE.md` 형식의 상세 구현 명세서를 별도로 작성해야 합니다.

## 📌 Milestones (우선순위 순)

1. **Knowledge Sync Bridge (DB Export/Import)**
   - 파편화된 기기 간 지식(`state.sqlite`)을 안전하게 동기화하기 위한 JSONL 브릿지 파이프라인.
   - Tombstone 처리 및 Timestamp 병합(Merge) 로직 구현.
   - 상세 명세: `03_knowledge_sync_bridge.md`

2. **Core RAG & Knowledge Distillation Stabilization**
   - 로컬 FTS5 + Qwen3 Reranker RAG 파이프라인 무결성 확보.
   - 사전 지식(Prior Knowledge) 큐레이션 파이프라인의 할루시네이션 및 Edge 유실 버그 수정.
   - 관련 user_report 항목: 3, 4, 5, 6, 7
   - 상세 명세: `02_stabilization.md`

3. **Native PDF Annotation System**
   - Zotero의 형광펜/메모 시스템을 옵시디언 내장 PDF Viewer로 자체 구현.
   - `pdf_annotations` 테이블을 Knowledge Sync Bridge에 태워 오프라인 동기화 달성.
   - 상세 명세: `04_pdf_annotation_system.md`

## 🤖 Multi-Agent Debate Protocol
Codex 및 Claude 요원은 각 서브 플랜을 구체화할 때 다음 롤(Roles)을 반드시 수행/시뮬레이션해야 합니다:
- **`schema_guardian`**: `state.sqlite` 및 `docs/specs/` 버전 동기화 무결성 방어.
- **`cli_regression_runner`**: 각 마일스톤에 맞춰 `testbed/` 회귀 테스트 시나리오 작성.
- **`source_pair_analyst`**: 지식 정제 및 어노테이션이 L1~L4 DAG에 미치는 영향 분석.

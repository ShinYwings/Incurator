# Knowledge Sync Bridge

기기 간 지식(`state.sqlite`) 파편화 문제 해결. JSONL 기반 Export/Import 파이프라인과 Tombstone 충돌 해결 로직 구현. PDF Annotation 마일스톤의 전제 조건.

- `backend/src/curator/db_sync.py` 신규 구현
- `wiki db export / wiki db import` CLI 추가
- 기기 종속 데이터(임베딩 등) Export 블랙리스트 정책
- 연관 USER_REPORT 항목: 없음 (독립 인프라 마일스톤)
# A — Syncthing Auto-Sync Design

Date: 2026-06-06
Status: DESIGN ARTIFACT
Scope: P2P Auto-Sync logic for `state.sqlite` using `sync.jsonl` and Obsidian Plugin event listeners.

## 0. Design constraints discovered from the codebase
- The existing SQLite DB uses Last-Write-Wins (LWW) resolution.
- `state.sqlite` holds all states, and `sync.jsonl` acts as the cross-device transport.
- The `curator.db_sync` module already handles LWW correctly for dry-run and actual runs.

## 0.5 Docs Specs & Invariants
- `SCHEMA.md` dictates that sync tombstones (`deleted_records`) must propagate safely.
- No cloud dependencies are allowed for the base sync; it must be fully P2P relying on the filesystem.

## 1. Auto-Sync Loop Prevention Layer
### 1.1 Alternatives & Trade-offs
- Option A: Write an `is_importing` state into the DB. (Pros: persistent. Cons: if the app crashes, the lock remains forever, breaking future syncs).
- Option B: Use `.curator/sync_meta.json` to store the last imported `sync.jsonl` hash or timestamp. (Pros: immune to crashes, deterministic. Cons: requires file IO).

### 1.2 Decision: Option B
**결정 사항**: Option B를 선택한다. `sync.jsonl`의 파일 수정 시간(mtime)이나 내용 해시를 기록하여, 변경된 파일만 Import하고 자신이 방금 내보낸 파일은 무시하게 만든다.

### 1.3 Implementation Logic
```python
def check_and_import():
    # If sync.jsonl mtime > last_import_mtime, run import_knowledge
    # Record new mtime
```

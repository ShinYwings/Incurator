# Syncthing & Git Sync Ignore Guide

이 가이드는 지식 베이스(Vault)를 여러 기기에서 동기화하거나 Git으로 관리할 때 유용한 제외(Ignore) 설정 모음입니다.

---

## 1. .stignore (Syncthing 전용)
Syncthing을 사용하여 실시간 동기화를 할 때, 데이터베이스 잠금 문제나 불필요한 충돌을 방지하기 위해 다음 항목들을 제외해야 합니다.

```text
// Git 내부 저장소 무시 (가장 중요)
.git/
scripts/

// OS 및 툴 관련 임시 파일
.DS_Store
Thumbs.db
.idea/
.vscode/
.venv/
__pycache__/
*.pyc
.env

// SQLite 임시 파일 (incurator 프로젝트용)
*.sqlite-*
*.db-*

// 에이전트 및 테스트베드 (선택 사항)
.claude/
testbed/
```

---

## 2. .gitignore (Git 전용)
Git으로 지식 베이스를 관리할 때 대용량 파일이나 로컬 상태를 제외하기 위한 설정입니다.

```gitignore
# ==========================================
# 1. Database & incurator Data (Syncthing 담당 권장)
# ==========================================
# DB 파일은 실시간 동기화 툴(Syncthing 등)에 맡기고 Git에서는 제외하는 것이 안전합니다.
*.sqlite*
*.db*
.curator/
qmd-cache/

# ==========================================
# 2. Obsidian Local State
# ==========================================
# 플러그인과 기본 세팅은 Git으로 백업하되, 현재 열려있는 탭 상태 등은 무시합니다.
.obsidian/workspace
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.trash/

# ==========================================
# 3. Python & Agent Environment
# ==========================================
.venv/
.idea/
.vscode/
.claude/
testbed/
scripts/dev/
build/
dist/
.ruff_cache/
.lock/
__pycache__/
*.pyc
*.swp
.env

# ==========================================
# 4. Syncthing & OS Files
# ==========================================
.stversions/
.stfolder/
*.sync-conflict-*
.DS_Store
Thumbs.db

# ==========================================
# 5. Large files (Optional)
# ==========================================
# 대용량 리소스나 에셋이 많을 경우 제외를 검토하세요.
04_Resources/
05_Assets/
```

testbed에 들어가있는 각 ignore 폴더라고 생각
---
# .stignore
// Git 내부 저장소 무시 (가장 중요)
.git/

// OS 및 툴 관련 임시 파일
.DS_Store
Thumbs.db
.idea/
.vscode/
.venv/
__pycache__/
*.pyc
.env

// SQLite 임시 파일 (llm-wiki 프로젝트용)
*.sqlite-*
*.db-*



# .gitignore
# ==========================================
# 1. Database & llm-wiki Data (Syncthing 담당)
# ==========================================
*.sqlite*
*.db*
.curator/
qmd-cache/

# ==========================================
# 2. Obsidian Local State
# ==========================================
# 플러그인과 기본 세팅은 Git으로 백업하되, 현재 열려있는 탭 상태는 무시합니다.
.obsidian/workspace
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.trash/

# ==========================================
# 3. Python & antigravity Agent Env
# ==========================================
# antigravity 에이전트 구동을 위한 파이썬 가상환경 및 캐시 무시
.venv/
.idea/
.vscode/
__pycache__/
*.pyc
.env

# 만약 antigravity가 생성하는 별도의 임시 로그나 상태 파일이 있다면 아래에 추가하세요.
# 예: antigravity_temp/ 

# ==========================================
# 4. Syncthing & OS Files
# ==========================================
.stversions/
.stfolder/
*.sync-conflict-*
.DS_Store
Thumbs.db

# ==========================================
# 5. Large files
# ==========================================
04_Resources/
05_Assets/

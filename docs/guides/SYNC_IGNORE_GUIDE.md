# Syncthing & Git Sync Ignore Guide

이 가이드는 지식 베이스(Vault)를 여러 기기에서 동기화하거나 Git으로 관리할 때 유용한 제외(Ignore) 설정 모음입니다.

---

## 1. .stignore (Syncthing 전용)

Syncthing을 사용하여 실시간 동기화를 할 때, 데이터베이스 잠금 문제나 불필요한 충돌을 방지하기 위해 다음 항목들을 제외해야 합니다.

```text
// Git 내부 저장소 및 서브모듈 설정 무시
.git
.git/
.gitmodules

// OS 및 툴 관련 임시 파일
.DS_Store
Thumbs.db
.idea/
.vscode/
.venv/
__pycache__/
*.pyc
.env

// SQLite 임시 파일 (Incurator 프로젝트용)
*.sqlite-*
*.db-*

// 의존성 폴더 무시 (Syncthing 부하 감소)
node_modules/
**/node_modules/

// Incurator plugin: backend 실행 경로가 기기마다 다르면 설정은 로컬로 유지
.obsidian/plugins/incurator-obsidian-agent/data.json

// Incurator backend: 기기별 인덱스 상태
// 다른 기기 위에 덮어쓰면 재인덱싱 필요; vault 파일은 Syncthing이 동기화
.curator/state.sqlite
.curator/qmd/index.sqlite

// 에이전트 및 테스트베드 (선택 사항)
.claude/
testbed/
```

> **참고**: `sessions.json`과 `data.json` 분리 구조
> 채팅 히스토리(`.curator/sessions.json`)는 안전한 보존과 동기화를 위해 플러그인 폴더 외부(`.curator/`)에 저장되며 세션 단위 병합과 삭제 tombstone을 지원합니다.
> backend 실행 파일 경로, MCP command, Zotero 경로처럼 기기마다 달라지는 UI 캐시/설정은 `.obsidian/plugins/.../data.json`에 저장되어 로컬로 유지됩니다.

### Obsidian Plugin 배포와 macOS/Linux 동기화

Incurator Obsidian plugin은 빌드 산출물인 `.obsidian/plugins/incurator-obsidian-agent/main.js`, `manifest.json`, `styles.css`가 active vault 안에 배포됩니다. Syncthing에서 `.obsidian/plugins/incurator-obsidian-agent/` 전체를 제외하지 않았다면 Linux에서 `plugin/deploy.sh`로 배포한 변경 사항은 macOS vault에도 동기화됩니다.

기기별로 달라야 하는 파일은 `data.json`처럼 ignore에 둡니다. 특히 MCP command 절대 경로나 backend 설치 경로처럼 Linux와 macOS에서 다른 값이 들어갈 수 있으면 `data.json` 동기화를 피하고 각 기기에서 설정합니다.

macOS에 Incurator가 전역 설치되어 있지 않다면 Obsidian plugin 설정에서 `Incurator MCP command`와 `Incurator MCP args`를 macOS 경로로 지정합니다. `uv`를 쓰는 예시는 `PLUGIN_GUIDE.md`의 세션 동기화 섹션을 참고하세요.

### Syncthing 기기 Registry

Obsidian plugin은 시작 시 로컬 Syncthing `config.xml`을 읽어서 현재 vault를 공유하는 기기 목록을 `.curator/devices.json`에 자동 기록합니다. Syncthing이 아는 정보는 device id, device name, folder id, folder label, 현재 기기의 folder path까지입니다.

backend 실행 경로는 Syncthing이 알 수 없으므로 Incurator가 기기별 entry로 기록합니다. 각 기기에서 한 번씩 실행하면 서로 다른 backend launcher를 같은 registry에서 볼 수 있습니다.

일반 사용에서는 명령어가 필요하지 않습니다. Syncthing이 플러그인 산출물을 동기화하고, 각 기기에서 Obsidian plugin이 로드되면 registry가 자동으로 갱신됩니다. 아래 CLI는 자동 갱신이 실패했거나 터미널에서 상태를 확인하고 싶을 때만 사용합니다.

```bash
wiki devices sync
wiki devices status
```

macOS에 `wiki`가 설치되어 있지 않고 repo의 backend를 `uv`로 실행해야 한다면:

```bash
wiki devices sync \
  --backend-command /opt/homebrew/bin/uv \
  --backend-args '["--directory", "/Users/<you>/Workspace/Incurator/backend", "run", "wiki", "mcp"]'
```

macOS에서 직접 배포해야 하는 경우에는 같은 스크립트에 macOS vault 경로를 넘깁니다.

```bash
cd /path/to/Incurator/plugin
OBSIDIAN_PLUGIN_DIR=/Users/<you>/path/to/second_brain/.obsidian/plugins/incurator-obsidian-agent ./deploy.sh
```

Syncthing으로 산출물이 도착했거나 macOS에서 직접 배포한 뒤에는 Obsidian에서 Incurator plugin을 reload하거나 Obsidian을 재시작합니다.

---

## 2. .gitignore (Git 전용)

Git으로 지식 베이스를 관리할 때 대용량 파일이나 로컬 상태를 제외하기 위한 설정입니다.

```gitignore
# ==========================================
# 1. Database & Incurator Data (Syncthing 담당 권장)
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

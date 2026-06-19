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

// Incurator backend: 기기별 DB 및 내부 검색 상태
// vault 파일은 Syncthing이 동기화하며 DB-native search row는 기기별로 재빌드
.curator/state.sqlite

// Incurator runtime: 백엔드 실시간 작업 상태 파일 (휘발성)
// 짧은 주기로 업데이트되므로 동기화 시 심각한 충돌과 트래픽 유발
.curator/runtime/

// Incurator 자동 동기화: 기기별 로컬 마크 (device_id, peer high-water mark)
// 반드시 로컬 유지 — 동기화되면 기기끼리 서로의 마크를 덮어써 재import 폭주를 유발.
// 주의: .curator/sync/ 는 제외하지 말 것 — dev-*.jsonl 지식 스냅샷은 Syncthing이 기기 간에 운반해야 함.
.curator/sync_state.json

// 에이전트 및 테스트베드 (선택 사항)
.claude/
testbed/
```

> [!IMPORTANT]
> 기기 간 자동 동기화(`wiki db autosync`)는 Syncthing이
> `.curator/sync/dev-<device_id>.jsonl` 스냅샷 파일을 운반하는 것에 의존합니다.
> `.curator/sync/`는 **동기화 유지**하고, `.curator/state.sqlite`와
> `.curator/sync_state.json`만 기기 로컬로 두세요. USER_GUIDE "기기 간 지식 동기화"와
> SYSTEM_BEHAVIOR §13.1 참고.

> **참고**: `sessions.json`과 `data.json` 분리 구조
> 채팅 히스토리(`.curator/sessions.json`)는 안전한 보존과 동기화를 위해 플러그인 폴더 외부(`.curator/`)에 저장되며 세션 단위 병합과 삭제 tombstone을 지원합니다.
> backend 실행 파일 경로, MCP command, Zotero 경로처럼 기기마다 달라지는 UI 캐시/설정은 `.obsidian/plugins/.../data.json`에 저장되어 로컬로 유지됩니다.
> 동기화된 세션은 Zotero attachment key, file hash, vault-relative path, page 같은 PDF portable identity를 보존할 수 있지만, PDF/Zotero 절대경로는 사용 전에 각 기기에서 검증하거나 다시 해석합니다.

### Obsidian Plugin 배포와 macOS/Linux 동기화

Incurator Obsidian plugin은 빌드 산출물인 `.obsidian/plugins/incurator-obsidian-agent/main.js`, `manifest.json`, `styles.css`가 active vault 안에 배포됩니다. Syncthing에서 `.obsidian/plugins/incurator-obsidian-agent/` 전체를 제외하지 않았다면 Linux에서 `plugin/deploy.sh`로 배포한 변경 사항은 macOS vault에도 동기화됩니다.

기기별로 달라야 하는 파일은 `data.json`처럼 ignore에 둡니다. 특히 backend command 절대 경로나 backend 설치 경로처럼 Linux와 macOS에서 다른 값이 들어갈 수 있으면 `data.json` 동기화를 피하고 각 기기에서 설정합니다.

macOS에 Incurator가 전역 설치되어 있지 않다면 Obsidian plugin 설정에서 `Backend command`와 `Backend arguments`를 macOS 경로로 지정합니다. `uv`를 쓰는 예시는 `PLUGIN_GUIDE_KR.md`의 세션 동기화 섹션을 참고하세요.

### Syncthing 기기 Registry

Obsidian plugin은 시작 시 로컬 Syncthing `config.xml`을 읽어서 현재 vault를 공유하는 기기 목록을 `.cache/config/devices.json`에 자동 기록합니다. Syncthing이 아는 정보는 device id, device name, folder id, folder label, 현재 기기의 folder path까지입니다.

backend 실행 경로는 Syncthing이 알 수 없으므로 Incurator가 기기별 entry로 기록합니다. 각 기기에서 한 번씩 실행하면 서로 다른 backend launcher를 같은 registry에서 볼 수 있습니다.

일반 사용에서는 명령어가 필요하지 않습니다. Syncthing이 플러그인 산출물을 동기화하고, 각 기기에서 Obsidian plugin이 로드되면 registry가 자동으로 갱신됩니다. 아래 CLI는 자동 갱신이 실패했거나 터미널에서 상태를 확인하고 싶을 때만 사용합니다.

갱신할 때마다 `.cache/config/devices.json`은 현재 Syncthing 폴더에 실제로 포함된 기기 목록과 다시 맞춰집니다. 아직 공유 중인 기기의 backend hint는 보존하지만, 더 이상 이 vault를 공유하지 않는 device id는 제거되어 오래된 기기가 dashboard에 계속 표시되지 않습니다.

```bash
wiki devices
wiki devices sync
wiki devices status
```

`wiki devices`는 `wiki devices status`의 단축 명령이며, 아직 backend launcher
hint가 없고 Syncthing metadata만 있는 기기도 registry에 있으면 표시합니다.

### 기기 간 Reference PDF

외부 PDF에 대해 **Add to Incurator**를 실행하면 backend는 `04_Resources/` 아래에
작은 markdown reference stub을 만들고, 실제 로컬 파일 경로는 backend source
metadata에 기록합니다. 이 stub은 vault와 함께 Syncthing으로 동기화될 수 있지만,
기기마다 Zotero나 외부 PDF 라이브러리의 mount 위치가 다를 수 있으므로 기본적으로
PDF 절대 경로를 포함하지 않아야 합니다.

의도한 공유 모델은 다음과 같습니다.

- `04_Resources/` reference stub: vault와 함께 Syncthing으로 동기화합니다. 크거나
  private한 resource library를 Git에 의존하지 않습니다.
- `.curator/Collections/`: 프로젝트가 원하면 생성된 knowledge artifact로 Git에
  versioning할 수 있습니다.
- `.curator/state.sqlite*`, `.curator/runtime/`: 기기별 runtime/index/휘발성 상태입니다.
  Syncthing이나 Git으로 공유하지 않습니다.
- backend 실행 파일/저장소 경로: 기기별 설정입니다. 공유 vault truth로 저장하지 않습니다.
- Zotero/external PDF 원본: 별도 Syncthing 폴더로 동기화할 수 있지만, Incurator는
  vault만 보고 그 경로를 알 수 없습니다. 각 기기에서 로컬 Zotero/external root로
  resolve하거나 rebind해야 합니다.

macOS에 `wiki`가 설치되어 있지 않고 repo의 backend를 `uv`로 실행해야 한다면:

```bash
wiki devices sync \
  --backend-command /opt/homebrew/bin/uv \
  --backend-args '["--directory", "/Users/<you>/Workspace/Incurator/backend", "run", "wiki", "mcp"]'
```

macOS에서 직접 배포해야 하는 경우에는 같은 스크립트에 macOS vault 경로를 넘깁니다.

```bash
cd /path/to/Incurator/plugin
OBSIDIAN_PLUGIN_DIR=/path/to/<vault>/.obsidian/plugins/incurator-obsidian-agent ./deploy.sh
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
tests/scenarios/
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

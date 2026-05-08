# Syncthing & Git Sync Ignore Guide

This guide provides a collection of ignore settings useful when synchronizing your knowledge base (Vault) across multiple devices or managing it with Git.

---

## 1. .stignore (Syncthing Exclusive)

When using Syncthing for real-time synchronization, you must exclude the following items to prevent database locking issues or unnecessary conflicts.

```text
// Ignore internal Git repository (Most Important)
.git/
scripts/

// OS and Tool-related temporary files
.DS_Store
Thumbs.db
.idea/
.vscode/
.venv/
__pycache__/
*.pyc
.env

// SQLite temporary files (For Incurator project)
*.sqlite-*
*.db-*

// Agent & Testbed (Optional)
.claude/
testbed/
```

---

## 2. .gitignore (Git Exclusive)

Settings to exclude large files or local state when managing your knowledge base with Git.

```gitignore
# ==========================================
# 1. Database & Incurator Data (Recommended for Syncthing)
# ==========================================
# It is safer to leave DB files to real-time sync tools (like Syncthing) and exclude them from Git.
*.sqlite*
*.db*
.curator/
qmd-cache/

# ==========================================
# 2. Obsidian Local State
# ==========================================
# Backup plugins and core settings with Git, but ignore temporary workspace states.
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
# Consider excluding large resources or assets if they are heavy.
04_Resources/
05_Assets/
```

---

## 💡 Best Practices

1.  **SQLite DB Management**: The `state.sqlite` file is frequently updated. Synchronizing this via Git often results in large commit sizes and merge conflicts. We recommend using **Syncthing** for real-time database sync and **Git** for markdown file versioning.
2.  **Conflict Prevention**: Ensure that database files in the `.curator/` directory are properly ignored to prevent corruption during simultaneous syncs.
3.  **Syncthing Tip**: After setting up your Vault folder in Syncthing, go to folder settings -> "Ignore Patterns" tab, and paste the contents of the `.stignore` section above.

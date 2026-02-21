#!/usr/bin/env bash
set -e

# ============================================================
# machina-cockpit entrypoint
# Runs before the base Code OSS entrypoint
# ============================================================

# --- Git config (if env vars provided) ---------------------------------------
if [ -n "$GIT_USER_NAME" ]; then
    git config --global user.name "$GIT_USER_NAME"
fi
if [ -n "$GIT_USER_EMAIL" ]; then
    git config --global user.email "$GIT_USER_EMAIL"
fi

# --- Verify Claude Code is available -----------------------------------------
if command -v claude &>/dev/null; then
    echo "[machina-cockpit] Claude Code: $(claude --version 2>/dev/null || echo 'installed')"
else
    echo "[machina-cockpit] WARNING: claude not found in PATH"
fi

# --- Auto-clone repos (comma-separated MACHINA_REPOS) ------------------------
if [ -n "$MACHINA_REPOS" ]; then
    CLONE_DIR="${MACHINA_CLONE_DIR:-/home/user/repos}"
    mkdir -p "$CLONE_DIR"
    IFS=',' read -ra REPOS <<< "$MACHINA_REPOS"
    for repo in "${REPOS[@]}"; do
        repo=$(echo "$repo" | xargs)  # trim whitespace
        repo_name=$(basename "$repo" .git)
        if [ ! -d "$CLONE_DIR/$repo_name" ]; then
            echo "[machina-cockpit] Cloning $repo -> $CLONE_DIR/$repo_name"
            git clone "$repo" "$CLONE_DIR/$repo_name" || echo "[machina-cockpit] Failed to clone $repo"
        else
            echo "[machina-cockpit] Repo already exists: $CLONE_DIR/$repo_name"
        fi
    done
fi

# --- Fall through to base image entrypoint -----------------------------------
# The Code OSS base image uses /google/scripts/entrypoint.sh
if [ -f /google/scripts/entrypoint.sh ]; then
    exec /google/scripts/entrypoint.sh "$@"
else
    exec "$@"
fi

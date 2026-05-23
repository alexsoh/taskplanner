#!/usr/bin/env bash
# TaskPlanner upgrade runner for Linux / macOS.
# Called by upgrade.sh after it has downloaded and extracted the new package.
# Do not run this directly.
#
# Usage (internal):
#   bash upgrade_run.sh --app-dir /path/to/taskplanner --source-path /path/to/extracted

set -euo pipefail

_early_fail() { echo "    [FAIL] upgrade_run.sh failed at line $1" >&2; exit 1; }
trap '_early_fail $LINENO' ERR

APP_DIR=""
SOURCE_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-dir)     APP_DIR="$2";     shift 2 ;;
    --source-path) SOURCE_PATH="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

if [ -z "$APP_DIR" ] || [ -z "$SOURCE_PATH" ]; then
  echo "Usage: upgrade_run.sh --app-dir DIR --source-path DIR"
  exit 1
fi

cd "$APP_DIR"

step()  { echo ""; echo "==> $1"; }
ok()    { echo "    [OK] $1"; }
fail()  { echo "    [FAIL] $1" >&2; }

TIMESTAMP=$(date +"%Y%m%d_%H%M")

PYTHON="${APP_DIR}/venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  step "No venv yet — bootstrapping local Python (same as first ./serve.sh run)..."
  bash "${APP_DIR}/serve.sh" --bootstrap-only --skip-build
  PYTHON="${APP_DIR}/venv/bin/python"
  if [ ! -x "$PYTHON" ]; then
    fail "venv still missing after bootstrap"
    exit 1
  fi
  ok "Local Python environment ready"
fi

CUR_VERSION=$("$PYTHON" -c "from tp import __version__; print(__version__)" 2>/dev/null || echo "unknown")
BACKUP_DIR="${APP_DIR}/backups/v${CUR_VERSION}_${TIMESTAMP}"

if [ -n "${TASKPLANNER_PORT:-}" ]; then
  PORT="$TASKPLANNER_PORT"
else
  PORT="8200"
fi

rollback() {
  fail "Upgrade failed. Rolling back..."
  step "Stopping any running server..."
  pkill -f "uvicorn tp.main:app" 2>/dev/null || true
  sleep 1

  if [ -d "$BACKUP_DIR" ]; then
    step "Restoring from backup $BACKUP_DIR..."
    EXCLUDES=("venv" "python" "node_modules" "logs" "data" "backups" ".git" ".req_hash")
    for item in "$BACKUP_DIR"/*/; do
      name=$(basename "$item")
      skip=0
      for ex in "${EXCLUDES[@]}"; do [[ "$name" == "$ex" ]] && skip=1 && break; done
      [ "$skip" -eq 1 ] && continue
      cp -r "$item" "$APP_DIR/"
    done
    find "$BACKUP_DIR" -maxdepth 1 -type f | while read -r f; do
      cp "$f" "$APP_DIR/"
    done
    ok "Restored from backup"
  fi

  mkdir -p "${APP_DIR}/logs"
  step "Restarting server..."
  nohup "$PYTHON" -m uvicorn tp.main:app --host 0.0.0.0 --port "$PORT" \
      >> "${APP_DIR}/logs/taskplanner.log" 2>&1 &
  ok "Server restarting (check logs for status)"
  exit 1
}

trap rollback ERR

step "Stopping TaskPlanner..."
if pkill -f "uvicorn tp.main:app" 2>/dev/null; then
  sleep 2
  ok "Server stopped"
else
  ok "Server was not running"
fi

step "Backing up current source to $BACKUP_DIR..."
mkdir -p "$BACKUP_DIR"
EXCLUDES=("venv" "python" "node_modules" "logs" "data" "backups" ".git" ".req_hash"
          "taskplanner_backup_*" "taskplanner_upgrade_tmp")
shopt -s nullglob
for item in "$APP_DIR"/*; do
  name=$(basename "$item")
  skip=0
  for ex in "${EXCLUDES[@]}"; do
    [[ "$name" == $ex ]] && skip=1 && break
  done
  [ "$skip" -eq 1 ] && continue
  cp -r "$item" "$BACKUP_DIR/"
done
shopt -u nullglob
ok "Backup created at $BACKUP_DIR"

# Explicitly preserve data directory (database with settings/token)
if [ -d "$APP_DIR/data" ]; then
  mkdir -p "$BACKUP_DIR/data"
  cp -r "$APP_DIR/data"/* "$BACKUP_DIR/data/" 2>/dev/null || true
  ok "Database backed up separately"
fi

step "Updating source files from $SOURCE_PATH..."
COPY_EXCLUDES=("venv" "python" "node_modules" "logs" "data" "backups" ".git" ".req_hash"
               "taskplanner_backup_*" "taskplanner_upgrade_tmp")
shopt -s nullglob
for item in "$SOURCE_PATH"/*; do
  name=$(basename "$item")
  skip=0
  for ex in "${COPY_EXCLUDES[@]}"; do [[ "$name" == $ex ]] && skip=1 && break; done
  [ "$skip" -eq 1 ] && continue
  cp -r "$item" "$APP_DIR/"
done
shopt -u nullglob
ok "Files updated"

req_hash=$(md5sum "${APP_DIR}/requirements.txt" 2>/dev/null | cut -d' ' -f1 \
           || shasum "${APP_DIR}/requirements.txt" | cut -d' ' -f1)
hash_file="${APP_DIR}/.req_hash"
stored_hash=$(cat "$hash_file" 2>/dev/null || echo "")

if [ "$req_hash" = "$stored_hash" ]; then
  ok "Python dependencies unchanged, skipping install"
else
  step "Updating Python dependencies..."
  PIP_REQUIRE_VENV=1 "$PYTHON" -m pip install --quiet -r requirements.txt
  echo -n "$req_hash" > "$hash_file"
  ok "Python dependencies updated"
fi

if [ ! -d "${APP_DIR}/frontend" ]; then
  step "Pre-built release -- using existing static/"
  ok "Skipped frontend build (compiled release)"
elif command -v npm &>/dev/null; then
  step "Rebuilding frontend..."
  cd "${APP_DIR}/frontend"
  npm install --silent
  npm run build --silent
  cd "$APP_DIR"
  ok "Frontend rebuilt"
elif [ -f "${APP_DIR}/static/index.html" ]; then
  step "Frontend: npm not found -- using existing pre-built static/"
  ok "Skipped (pre-built static/ is present)"
else
  fail "No pre-built frontend and npm not found. Install Node.js 18+ to rebuild."
  exit 1
fi

mkdir -p "${APP_DIR}/logs"
step "Starting TaskPlanner..."
nohup "$PYTHON" -m uvicorn tp.main:app --host 0.0.0.0 --port "$PORT" \
    >> "${APP_DIR}/logs/taskplanner.log" 2>&1 &
ok "Server started (PID $!, port $PORT)"

sleep 5

step "Verifying service..."
if curl -sf "http://localhost:${PORT}/api/health" > /dev/null 2>&1; then
  ok "Service is running and healthy"
else
  echo "    Health check failed -- server may still be starting up. Check logs/"
fi

# Verify database integrity and settings
step "Verifying settings persistence..."
SETTINGS_CHECK=$("$PYTHON" << 'PYTHON_EOF'
import sqlite3
from pathlib import Path
import sys

db_path = Path("data/taskplanner.db")
if not db_path.exists():
    print("ERROR: Database not found")
    sys.exit(1)

try:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT upgrade_token FROM app_settings WHERE id=1")
    result = cursor.fetchone()
    if result and result[0]:
        print(f"OK: upgrade_token preserved: {result[0][:10]}...")
    else:
        print("WARNING: upgrade_token is empty/NULL")
    conn.close()
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
PYTHON_EOF
)
echo "    $SETTINGS_CHECK"

echo ""
echo "=== Upgrade complete! ==="
echo "  Backup:  $BACKUP_DIR"
echo "  Web UI:  http://localhost:${PORT}"
echo ""

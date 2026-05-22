#!/usr/bin/env bash
# TaskPlanner bootstrap upgrader for Linux / macOS.
# Downloads the latest compiled release from the evalex server, then runs
# upgrade_run.sh from the newly downloaded package so the upgrade logic
# is always current.
#
# Usage:
#   ./upgrade.sh --token evlx_xxxxxxxxxxxx
#   ./upgrade.sh --source-path /path/to/new-taskplanner
#
# Options:
#   --token TOKEN        Evalex download token (required for downloading)
#   --source-path PATH   Use a local folder instead of downloading
#   --evalex-base URL    Base URL for the evalex server

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------- parse arguments ----------
TOKEN=""
SOURCE_PATH=""
EVALEX_BASE="https://evalex.duckdns.org"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --token)        TOKEN="$2";       shift 2 ;;
    --source-path)  SOURCE_PATH="$2"; shift 2 ;;
    --source)       SOURCE_PATH="$2"; shift 2 ;;
    --evalex-base)  EVALEX_BASE="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

EVALEX_BASE="${EVALEX_BASE%/}"
APP_SLUG="taskplanner"
EXTRACT_DIR="${SCRIPT_DIR}/taskplanner_upgrade_tmp"
RUNNER_SOURCE=""

cleanup() {
  if [ -z "$SOURCE_PATH" ] && [ -d "$EXTRACT_DIR" ]; then
    rm -rf "$EXTRACT_DIR"
  fi
}
trap cleanup EXIT

if [ -n "$SOURCE_PATH" ]; then
  RUNNER_SOURCE="$SOURCE_PATH"
  echo "Using local source: $SOURCE_PATH"
else
  if [ -z "$TOKEN" ]; then
    echo "[FAIL] Download token is required. Pass --token evlx_..."
    exit 1
  fi

  RAW_OS=$(uname -s | tr '[:upper:]' '[:lower:]')
  RAW_ARCH=$(uname -m)

  case "$RAW_OS" in
    darwin) PLAT_OS="macos" ;;
    linux)  PLAT_OS="linux" ;;
    *)      PLAT_OS="$RAW_OS" ;;
  esac

  case "$RAW_ARCH" in
    x86_64|amd64) PLAT_ARCH="x64" ;;
    arm64|aarch64) PLAT_ARCH="arm64" ;;
    *)             PLAT_ARCH="$RAW_ARCH" ;;
  esac

  ZIP_PATH="${SCRIPT_DIR}/taskplanner_update.zip"
  DOWNLOAD_URL="${EVALEX_BASE}/api/download?token=${TOKEN}&app=${APP_SLUG}&os=${PLAT_OS}&arch=${PLAT_ARCH}"

  echo ""
  echo "==> Downloading release from ${EVALEX_BASE} (${PLAT_OS}/${PLAT_ARCH})..."
  HTTP_CODE=$(curl -sS -w "%{http_code}" -o "$ZIP_PATH" "$DOWNLOAD_URL")

  if [ "$HTTP_CODE" = "403" ]; then
    rm -f "$ZIP_PATH"
    echo "    [FAIL] Download token is invalid, expired, or not authorized (403)."
    exit 1
  elif [ "$HTTP_CODE" = "404" ]; then
    rm -f "$ZIP_PATH"
    echo "    [FAIL] No ${PLAT_OS}/${PLAT_ARCH} release available. Try again later (404)."
    exit 1
  elif [ "$HTTP_CODE" != "200" ]; then
    rm -f "$ZIP_PATH"
    echo "    [FAIL] Download failed (HTTP ${HTTP_CODE})."
    exit 1
  fi
  echo "    [OK] Downloaded release zip"

  echo ""
  echo "==> Extracting package..."
  rm -rf "$EXTRACT_DIR"
  unzip -q "$ZIP_PATH" -d "$EXTRACT_DIR"
  rm -f "$ZIP_PATH"

  INNER_DIR=$(find "$EXTRACT_DIR" -mindepth 1 -maxdepth 1 -type d | head -1)
  RUNNER_SOURCE="$INNER_DIR"
  echo "    [OK] Extracted to $RUNNER_SOURCE"
fi

RUNNER="${RUNNER_SOURCE}/upgrade_run.sh"
if [ ! -f "$RUNNER" ]; then
  echo "upgrade_run.sh not found in package at $RUNNER_SOURCE"
  exit 1
fi

echo ""
echo "==> Running upgrade logic from new package..."
chmod +x "$RUNNER" 2>/dev/null || true

set +e
bash "$RUNNER" --app-dir "$SCRIPT_DIR" --source-path "$RUNNER_SOURCE"
rc=$?
set -e

if [ $rc -ne 0 ]; then
  echo ""
  echo "==> [FAIL] upgrade_run.sh exited with code $rc" >&2
  echo "    Check the output above for details." >&2
  exit $rc
fi

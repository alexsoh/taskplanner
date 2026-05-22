#!/usr/bin/env bash
# TaskPlanner local server (macOS/Linux): project-local Python under ./python/ + venv/ (no OS python3 on PATH
# for bootstrap), npm frontend build unless skipped, then uvicorn.
#
# Usage:
#   bash serve.sh                 # venv + deps + FE build + start (port 8200 or TASKPLANNER_PORT)
#   bash serve.sh 8200            # custom port
#   bash serve.sh --skip-build    # skip frontend npm build
#   bash serve.sh --bootstrap-only [--skip-build]   # venv + deps (+ FE unless skip); exit (used by upgrade_run.sh)
#   bash serve.sh --help
#
# Env (optional): TASKPLANNER_PYTHON, TASKPLANNER_PBS_TAG, TASKPLANNER_PYTHON_MM, TASKPLANNER_PORT. Vendored Python needs curl or wget.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TASKPLANNER_PBS_TAG="${TASKPLANNER_PBS_TAG:-20250212}"
TASKPLANNER_PYTHON_MM="${TASKPLANNER_PYTHON_MM:-3.11.11}"
PBS_BASE="https://github.com/astral-sh/python-build-standalone/releases/download/${TASKPLANNER_PBS_TAG}"

SKIP_BUILD=false
BOOTSTRAP_ONLY=false
PORT=""

# --- Help (any position) ---
for _a in "$@"; do
  if [[ "$_a" == "--help" ]]; then
    cat <<EOF
TaskPlanner development server with frontend build

Usage:
  bash serve.sh                    Build frontend and start (port 8200 or TASKPLANNER_PORT)
  bash serve.sh 8200               Custom port
  bash serve.sh --skip-build       Start without rebuilding frontend
  bash serve.sh --bootstrap-only   Create ./python/ if needed, venv, pip install, then exit (no server)
  bash serve.sh --bootstrap-only --skip-build   Same but no npm (e.g. release tree with static/ only)
  bash serve.sh --help             This help

Project-local Python:
  Uses only ./python/ (reuse or download standalone CPython) or TASKPLANNER_PYTHON — not OS python3 on PATH.
  Dependencies install only under venv/ (PIP_REQUIRE_VENV).

Other:
  - Node.js + npm on PATH when a frontend build is required (not used with --skip-build).
  - Press Ctrl+C to stop the server.
EOF
    exit 0
  fi
done

for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=true ;;
    --bootstrap-only) BOOTSTRAP_ONLY=true ;;
    --help) ;;
    *)
      if [[ "$arg" =~ ^[0-9]+$ ]]; then
        PORT="$arg"
      else
        echo "taskplanner: Unknown argument: $arg (try --help)" >&2
        exit 1
      fi
      ;;
  esac
done

if [ "$SKIP_BUILD" = false ] && [ "$BOOTSTRAP_ONLY" = false ]; then
  NEED_NPM=true
elif [ "$SKIP_BUILD" = false ] && [ "$BOOTSTRAP_ONLY" = true ]; then
  NEED_NPM=true
else
  NEED_NPM=false
fi

NPM=""
if [ "$NEED_NPM" = true ]; then
  if command -v npm &>/dev/null; then
    NPM="npm"
  else
    echo "taskplanner: npm not found. Install Node.js or use --skip-build." >&2
    exit 1
  fi
  echo "📦 Using npm: $(npm --version)"
fi

python_ok() {
  local exe="$1"
  [[ -n "$exe" && -x "$exe" ]] && "$exe" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null
}

first_executable() {
  local p
  for p in "$@"; do
    if [[ -n "$p" && -x "$p" ]]; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

taskplanner_download() {
  local url="$1" out="$2"
  if [[ -x /usr/bin/curl ]]; then
    /usr/bin/curl -fsSL --retry 3 --retry-delay 2 "$url" -o "$out"
    return
  fi
  if [[ -x /bin/curl ]]; then
    /bin/curl -fsSL --retry 3 --retry-delay 2 "$url" -o "$out"
    return
  fi
  if [[ -x /usr/bin/wget ]]; then
    /usr/bin/wget -q -O "$out" "$url"
    return
  fi
  echo "taskplanner: need curl or wget to download Python." >&2
  exit 1
}

pbs_asset_name() {
  local os arch gnu="gnu"
  os="$(uname -s)"
  arch="$(uname -m)"
  case "$os" in
    Darwin)
      case "$arch" in
        arm64) echo "cpython-${TASKPLANNER_PYTHON_MM}+${TASKPLANNER_PBS_TAG}-aarch64-apple-darwin-install_only.tar.gz" ;;
        x86_64) echo "cpython-${TASKPLANNER_PYTHON_MM}+${TASKPLANNER_PBS_TAG}-x86_64-apple-darwin-install_only.tar.gz" ;;
        *) echo "taskplanner: unsupported macOS CPU: $arch" >&2; return 1 ;;
      esac
      ;;
    Linux)
      if /usr/bin/ldd /bin/sh 2>/dev/null | grep -q musl; then gnu="musl"; fi
      case "$arch" in
        x86_64) echo "cpython-${TASKPLANNER_PYTHON_MM}+${TASKPLANNER_PBS_TAG}-x86_64-unknown-linux-${gnu}-install_only.tar.gz" ;;
        aarch64|arm64) echo "cpython-${TASKPLANNER_PYTHON_MM}+${TASKPLANNER_PBS_TAG}-aarch64-unknown-linux-${gnu}-install_only.tar.gz" ;;
        *) echo "taskplanner: unsupported Linux CPU: $arch" >&2; return 1 ;;
      esac
      ;;
    *)
      echo "taskplanner: automatic Python install is only for macOS and Linux." >&2
      echo "taskplanner: set TASKPLANNER_PYTHON to a Python 3.10+ interpreter, or use Windows setup.ps1." >&2
      return 1
      ;;
  esac
}

ensure_vendored_python() {
  local asset url tmp top pyb
  asset="$(pbs_asset_name)" || exit 1
  url="${PBS_BASE}/${asset}"
  echo "==> Downloading standalone Python ${TASKPLANNER_PYTHON_MM} (${TASKPLANNER_PBS_TAG}) into ./python/ ..." >&2
  tmp="$(mktemp -d)"
  taskplanner_download "$url" "${tmp}/p.tar.gz"
  rm -rf "${SCRIPT_DIR}/python"
  tar -xzf "${tmp}/p.tar.gz" -C "${tmp}"
  if [[ -d "${tmp}/python" ]]; then
    mv "${tmp}/python" "${SCRIPT_DIR}/python"
  else
    top="$(find "${tmp}" -maxdepth 1 -mindepth 1 -type d ! -name '.*' | head -1)"
    if [[ -z "$top" ]]; then
      echo "taskplanner: could not unpack Python tarball" >&2
      rm -rf "$tmp"
      exit 1
    fi
    mv "$top" "${SCRIPT_DIR}/python"
  fi
  rm -rf "$tmp"
  pyb="$(first_executable \
    "${SCRIPT_DIR}/python/bin/python3.11" \
    "${SCRIPT_DIR}/python/bin/python3.12" \
    "${SCRIPT_DIR}/python/bin/python3" \
    "${SCRIPT_DIR}/python/bin/python")" || true
  if [[ -z "${pyb:-}" ]]; then
    echo "taskplanner: no python binary under ${SCRIPT_DIR}/python/bin" >&2
    exit 1
  fi
  echo "$pyb"
}

resolve_bootstrap_python() {
  local p
  if [[ -n "${TASKPLANNER_PYTHON:-}" ]]; then
    if [[ ! -x "$TASKPLANNER_PYTHON" ]]; then
      echo "taskplanner: TASKPLANNER_PYTHON is not an executable file: $TASKPLANNER_PYTHON" >&2
      exit 1
    fi
    if ! python_ok "$TASKPLANNER_PYTHON"; then
      echo "taskplanner: TASKPLANNER_PYTHON must be Python 3.10 or newer: $TASKPLANNER_PYTHON" >&2
      exit 1
    fi
    echo "$TASKPLANNER_PYTHON"
    return 0
  fi
  p="$(first_executable \
    "${SCRIPT_DIR}/python/bin/python3.11" \
    "${SCRIPT_DIR}/python/bin/python3.12" \
    "${SCRIPT_DIR}/python/bin/python3" \
    "${SCRIPT_DIR}/python/bin/python")" || true
  if [[ -n "${p:-}" ]] && python_ok "$p"; then
    echo "$p"
    return 0
  fi
  ensure_vendored_python
}

if [ -x "$SCRIPT_DIR/venv/bin/python" ]; then
  VPY="$SCRIPT_DIR/venv/bin/python"
else
  BOOT="$(resolve_bootstrap_python)"
  echo "📦 Creating virtual environment (venv/)..."
  "$BOOT" -m venv "$SCRIPT_DIR/venv"
  VPY="$SCRIPT_DIR/venv/bin/python"
fi

export PIP_REQUIRE_VENV=1
echo "📦 Using Python: $VPY"

echo ""
echo "📦 Installing / refreshing Python dependencies..."
PIP_REQUIRE_VENV=1 "$VPY" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"

if [ "$SKIP_BUILD" = false ]; then
  if [ ! -d "$SCRIPT_DIR/frontend" ]; then
    echo "taskplanner: frontend/ not found — use --skip-build when only pre-built static/ is shipped (release zip)." >&2
    exit 1
  fi
  echo ""
  echo "🔨 Building frontend..."
  cd "$SCRIPT_DIR/frontend"
  if [ ! -d "node_modules" ]; then
    echo "   Installing npm dependencies..."
    $NPM install
  fi
  $NPM run build
  cd "$SCRIPT_DIR"
  echo "✅ Frontend build complete"
fi

if [ -z "$PORT" ]; then
  if [ -n "${TASKPLANNER_PORT:-}" ]; then
    PORT="$TASKPLANNER_PORT"
  else
    PORT="8200"
  fi
fi

if [ "$BOOTSTRAP_ONLY" = true ]; then
  echo ""
  echo "=== TaskPlanner bootstrap complete (venv + dependencies). Not starting the server. ==="
  exit 0
fi

echo ""
echo "🚀 Starting TaskPlanner on http://localhost:$PORT"
echo "   Press Ctrl+C to stop"
echo ""

exec "$VPY" -m uvicorn tp.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --reload

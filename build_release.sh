#!/usr/bin/env bash
# Build a compiled release of TaskPlanner for macOS or Linux.
# Compiles tp/ into a native .so via Nuitka, builds the frontend,
# and assembles a distributable zip with no source code.
#
# Prerequisites (build machine only):
#   - Python 3.11 with pip
#   - C compiler (clang on macOS, gcc on Linux)
#   - Node.js 18+ and npm
#
# Usage:
#   ./build_release.sh                    # build for current version
#
# Note: This is called by scripts/publish-release.sh --build or by GitHub Actions.
# GitHub Actions automatically uploads to the release.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------- detect platform ----------
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

if [ -f "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

VERSION=$("$PYTHON" -c "from tp import __version__; print(__version__)")
RELEASE_NAME="taskplanner-${VERSION}-${OS}-${ARCH}"

echo ""
echo "========================================="
echo "  TaskPlanner Release Builder"
echo "========================================="
echo "  Version:  ${VERSION}"
echo "  Platform: ${OS}-${ARCH}"
echo "  Python:   $("$PYTHON" --version 2>&1)"
echo ""

# ---------- 1. build frontend ----------
echo "==> [1/3] Building frontend..."
cd frontend
if [ ! -d "node_modules" ]; then
    npm install --silent
fi
npm run build --silent
cd "$SCRIPT_DIR"
echo "    [OK] Frontend built to static/"

# ---------- 2. compile backend ----------
echo ""
echo "==> [2/3] Compiling backend with Nuitka..."
"$PYTHON" -m pip install --quiet nuitka ordered-set

"$PYTHON" -m nuitka --module tp --include-package=tp --assume-yes-for-downloads

echo "    [OK] Backend compiled"

# ---------- 3. assemble release ----------
echo ""
echo "==> [3/3] Assembling release..."
RELEASE_DIR="release/${RELEASE_NAME}"
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

cp tp.cpython-*.so "$RELEASE_DIR/"
cp -r static "$RELEASE_DIR/"
cp requirements.txt "$RELEASE_DIR/"

for f in serve.sh upgrade.sh upgrade_run.sh setup.sh; do
    if [ -f "$f" ]; then
        cp "$f" "$RELEASE_DIR/"
        chmod +x "$RELEASE_DIR/$f"
    fi
done

echo "$VERSION" > "$RELEASE_DIR/version.txt"
cp README.md "$RELEASE_DIR/" 2>/dev/null || true

echo "    [OK] Release assembled in $RELEASE_DIR"

# ---------- 4. zip ----------
echo ""
echo "==> Creating zip..."
cd release
zip -rq "${RELEASE_NAME}.zip" "${RELEASE_NAME}"
cd "$SCRIPT_DIR"

ZIP_SIZE=$(du -sh "release/${RELEASE_NAME}.zip" | cut -f1)
echo "    [OK] release/${RELEASE_NAME}.zip ($ZIP_SIZE)"

# ---------- cleanup nuitka build artifacts ----------
rm -rf tp.build/
rm -f tp.cpython-*.so

echo ""
echo "========================================="
echo "  Build complete!"
echo "  release/${RELEASE_NAME}.zip"
echo "========================================="
echo ""

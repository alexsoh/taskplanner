#!/usr/bin/env bash
# macOS/Linux setup script for TaskPlanner.
# Installs Python dependencies and builds the frontend without starting the server.
# Usage: ./setup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "========================================"
echo "  TaskPlanner Setup"
echo "========================================"

bash "$SCRIPT_DIR/serve.sh" --bootstrap-only

echo ""
echo "========================================"
echo "  Setup complete!"
echo "========================================"
echo ""
echo "  To start TaskPlanner:"
echo "    ./serve.sh"
echo ""

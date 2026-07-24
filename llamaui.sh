#!/usr/bin/env bash
# llamaUI — cross-platform launcher (Linux / macOS / any Unix)
# Usage: ./llamaui.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# --- dependency check ---
need_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "ERROR: $1 is required but not found." >&2
        echo "  Install it with:  pip install $2" >&2
        exit 1
    fi
}

need_cmd python3 "python3 PySide6"

# --- auto-install PySide6 if missing ---
python3 -c "import PySide6" 2>/dev/null || {
    echo "PySide6 not found — installing…"
    pip3 install --user PySide6
}

# --- launch ---
exec python3 -m qt_app "$@"

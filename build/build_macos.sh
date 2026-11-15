#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Build a standalone AutoTyper for macOS.
#
# Produces dist/AutoTyper.app. Requires Python 3.11+ (python3 on PATH).
#
# Usage:  bash build/build_macos.sh
#
# Note on signing: unsigned apps still run locally after right-click > Open, but
# they cannot be distributed to other Macs without notarisation. To sign:
#   codesign --deep --force --options runtime \
#     --sign "Developer ID Application: Your Name (TEAMID)" dist/AutoTyper.app
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

VENV=".venv"
PY="${PYTHON:-python3}"

echo "=== AutoTyper macOS build ==="

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "ERROR: $PY was not found. Install Python 3.11+ (brew install python@3.12)." >&2
  exit 1
fi

if [ ! -d "$VENV" ]; then
  echo "Creating virtual environment in $VENV ..."
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "Installing dependencies ..."
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt pyinstaller

echo "Generating icons ..."
python assets/make_icon.py

echo "Running tests ..."
python -m pytest -q || echo "WARNING: tests failed; fix them before shipping."

echo "Building the .app bundle ..."
pyinstaller build/autotyper.spec --noconfirm --clean

echo
echo "Build complete: dist/AutoTyper.app"
echo "Run it with:  open dist/AutoTyper.app"
echo "Then grant Accessibility permission in System Settings (see README)."

if [ "${SIGN_IDENTITY:-}" != "" ]; then
  echo "Signing with ${SIGN_IDENTITY} ..."
  codesign --deep --force --options runtime --sign "$SIGN_IDENTITY" dist/AutoTyper.app
  echo "Signed."
fi

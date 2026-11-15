#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Build a standalone AutoTyper for Linux.
#
# Produces dist/AutoTyper/AutoTyper plus a launcher-friendly tarball.
#
# Usage:  bash build/build_linux.sh
#
# Notes:
#   * Global hotkeys and synthetic keystrokes require an X11 session (Xorg).
#     Under Wayland, run with QT_QPA_PLATFORM=xcb (XWayland) at best.
#   * On Debian/Ubuntu build hosts install: python3-venv python3-dev
#     libxcb-cursor0 libxkbcommon-x11-0 libdbus-1-3 libxcb-icccm4 libxcb-keysyms1
#     libxcb-shape0 libxcb-xinerama0 libxcb-randr0 libxcb-render-util0
#     libxcb-image0 libxcb-xfixes0
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

VENV=".venv"
PY="${PYTHON:-python3}"

echo "=== AutoTyper Linux build ==="

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "ERROR: $PY was not found. Install Python 3.11+ (sudo apt install python3-venv)." >&2
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

echo "Building the application directory ..."
pyinstaller build/autotyper.spec --noconfirm --clean

echo "Creating desktop entry and tarball ..."
VERSION="$(python -c 'import autotyper; print(autotyper.__version__)')"
STAGE="dist/autotyper-${VERSION}-linux-x86_64"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -r dist/AutoTyper/* "$STAGE/"

cat > "$STAGE/autotyper.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=AutoTyper
Comment=Type text anywhere with human-like timing
Exec=AutoTyper/AutoTyper
Icon=autotyper
Terminal=false
Categories=Utility;
EOF
cp assets/autotyper-256.png "$STAGE/autotyper.png"

(cd dist && tar -czf "autotyper-${VERSION}-linux-x86_64.tar.gz" "autotyper-${VERSION}-linux-x86_64")

echo
echo "Build complete:"
echo "  dist/AutoTyper/AutoTyper"
echo "  dist/autotyper-${VERSION}-linux-x86_64.tar.gz"
echo "Run it from an X11 (Xorg) session for global hotkeys to work."

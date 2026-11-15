#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Build AutoTyper for the platform this script runs on.
#
# Usage:  bash build/build.sh
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

case "$(uname -s)" in
  Darwin*)  exec bash build/build_macos.sh ;;
  Linux*)   exec bash build/build_linux.sh ;;
  MINGW*|MSYS*|CYGWIN*)
            echo "Use build\\build_windows.bat from a normal Command Prompt." >&2
            exit 1 ;;
  *)
            echo "Unsupported platform: $(uname -s)" >&2
            exit 1 ;;
esac

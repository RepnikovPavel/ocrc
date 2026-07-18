#!/usr/bin/env sh
# One-line install:
#   curl -fsSL https://raw.githubusercontent.com/RepnikovPavel/ocrc/main/install.sh | sh
#
# Copies a single Python file onto PATH. No pip, no virtualenv, no dependencies —
# ocrc is standard library only, which is what makes this safe to run anywhere.
set -eu

REPO="${OCRC_REPO:-https://raw.githubusercontent.com/RepnikovPavel/ocrc/main}"
BIN_DIR="${OCRC_BIN_DIR:-}"

if [ -z "$BIN_DIR" ]; then
    if [ -w /usr/local/bin ] 2>/dev/null; then BIN_DIR=/usr/local/bin
    else BIN_DIR="$HOME/.local/bin"; fi
fi
mkdir -p "$BIN_DIR"

command -v python3 >/dev/null 2>&1 || { echo "ocrc: python3 is required" >&2; exit 1; }
python3 - <<'PY' || { echo "ocrc: python >= 3.8 is required" >&2; exit 1; }
import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)
PY

TARGET="$BIN_DIR/ocrc"
if [ -f "./dont_read_me_src/ocrc.py" ]; then
    cp ./dont_read_me_src/ocrc.py "$TARGET"          # installing from a clone
else
    curl -fsSL "$REPO/dont_read_me_src/ocrc.py" -o "$TARGET"
fi
chmod +x "$TARGET"

echo "installed: $TARGET"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "note: $BIN_DIR is not on PATH — add it, or call $TARGET directly" ;;
esac
"$TARGET" --version

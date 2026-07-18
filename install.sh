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

# Ensure $BIN_DIR is on PATH for interactive AND non-interactive shells. A bare
# "note:" is easy to miss when piped through `sh`, leaving `ocrc` uncallable
# from the next ssh / non-login shell (issue ocr#7). We add a single guarded
# export line to the first existing rc file, marked so re-runs are idempotent.
ensure_on_path() {
    case ":$PATH:" in
        *":$BIN_DIR:"*) return 0 ;;
    esac
    [ -d "$BIN_DIR" ] || return 0
    _marker='# ocrc: added by install.sh'
    _line="export PATH=\"\$PATH:$BIN_DIR\"  $_marker"
    # Prefer .bashrc (most shells source it); fall back to .profile / .shrc
    _rc=""
    for _cand in "$HOME/.bashrc" "$HOME/.profile" "$HOME/.shrc"; do
        if [ -f "$_cand" ] || [ -w "$HOME" ]; then _rc="$_cand"; break; fi
    done
    [ -n "$_rc" ] || return 0
    if grep -qF "$_marker" "$_rc" 2>/dev/null; then
        :
    else
        printf '\n%s\n' "$_line" >> "$_rc"
        echo "added '$BIN_DIR' to PATH via $_rc (new shells will pick it up)"
    fi
}
ensure_on_path

"$TARGET" --version

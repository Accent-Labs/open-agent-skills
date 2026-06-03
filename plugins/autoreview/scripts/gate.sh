#!/bin/sh
# Autoreview fail-open wrapper. Locates python3, runs the gate, normalizes exits so only an
# intentional review-block (exit 2) blocks the commit. ANY problem -> exit 0 (fail-open).
ROOT="${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}"
SELF_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ -n "$ROOT" ] || ROOT="$SELF_DIR/.."
GATE="$ROOT/scripts/gate.py"
[ -f "$GATE" ] || GATE="$SELF_DIR/gate.py"

if [ "$AUTOREVIEW_NO_PY" = "1" ]; then
  PY=""
elif [ -x /usr/bin/python3 ]; then
  PY=/usr/bin/python3
else
  PY=$(command -v python3 || command -v python)
fi

if [ -z "$PY" ]; then
  echo "[autoreview] python3 not found; allowing commit (fail-open)" >&2
  exit 0
fi
if [ ! -f "$GATE" ]; then
  echo "[autoreview] gate.py not found; allowing commit (fail-open)" >&2
  exit 0
fi

"$PY" "$GATE"
code=$?
[ "$code" -eq 0 ] && exit 0
[ "$code" -eq 2 ] && exit 2
echo "[autoreview] gate exited $code; allowing commit (fail-open)" >&2
exit 0

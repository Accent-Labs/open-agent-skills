#!/bin/sh
here="$(cd "$(dirname "$0")" && pwd)"
python3 -m unittest discover -s "$here/tests" -t "$here" "$@" || exit $?
exec python3 "$here/../eval/run_eval.py"

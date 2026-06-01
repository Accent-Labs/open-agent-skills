#!/bin/sh
here="$(cd "$(dirname "$0")" && pwd)"
exec python3 -m unittest discover -s "$here/tests" -t "$here" "$@"

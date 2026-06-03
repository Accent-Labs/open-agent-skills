#!/usr/bin/env python3
"""Autoreview hook entrypoint. Invoked as: python3 <plugin>/scripts/gate.py  (JSON on stdin)."""
import os
import sys

# scripts/ is already first on sys.path when run as a script; be explicit for symlink-robustness.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from autoreview.cli import main  # noqa: E402

if __name__ == "__main__":
    main()

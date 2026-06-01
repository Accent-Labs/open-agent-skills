#!/usr/bin/env python3
"""Print the active coding-tool profile as JSON (used by the autoreview skill's spawn branch)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from autoreview.tools import detect_tool  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(detect_tool()))

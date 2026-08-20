"""Load the project environment before Python-based tools initialize.

Python imports ``sitecustomize`` during normal startup, which lets direct
``python3 -m pytest`` runs see the same project environment as Make targets.
"""
from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"


if ENV_FILE.is_file():
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = os.path.expandvars(value.strip())
        if key and value:
            os.environ.setdefault(key, value)

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def _load_project_env() -> None:
    if not ENV_FILE.is_file():
        return
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = os.path.expandvars(value.strip())
        if key and value:
            os.environ.setdefault(key, value)


_load_project_env()

if os.environ.get("PYTHONPYCACHEPREFIX"):
    sys.pycache_prefix = os.path.abspath(os.path.expanduser(os.environ["PYTHONPYCACHEPREFIX"]))

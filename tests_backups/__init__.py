from __future__ import annotations

import atexit
import os
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_ENV_FILE = _ROOT / ".env"


def _load_project_env() -> None:
    if not _ENV_FILE.is_file():
        return
    for raw in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = os.path.expandvars(value.strip())
        if key and value:
            os.environ.setdefault(key, value)


_load_project_env()
_CACHE_ROOT = Path(os.path.expanduser(os.environ.get("PYTHON_CACHE_DIR", "/tmp/tony-ai-pycache")))
_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["PYTHON_CACHE_DIR"] = str(_CACHE_ROOT)
os.environ["PYTHONPYCACHEPREFIX"] = str(_CACHE_ROOT)
if hasattr(sys, "pycache_prefix"):
    sys.pycache_prefix = str(_CACHE_ROOT)


def _cleanup_local_bytecode() -> None:
    """Remove pytest's bootstrap cache if its importer created one locally."""
    shutil.rmtree(_ROOT / "tests" / "__pycache__", ignore_errors=True)
    shutil.rmtree(_ROOT / "__pycache__", ignore_errors=True)


atexit.register(_cleanup_local_bytecode)

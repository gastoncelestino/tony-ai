"""Keep Python bytecode outside the repository checkout."""

from __future__ import annotations

import os
import sys
from pathlib import Path

runtime_dir = Path(os.environ.get("TONY_RUNTIME_DIR", "~/.tony-ai/tony-ai")).expanduser()
runtime_dir.mkdir(parents=True, exist_ok=True)
sys.pycache_prefix = str(runtime_dir / "pycache")

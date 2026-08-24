"""Tony Kernel — minimal execution core.
Registra una limpieza al cerrar el proceso para eliminar las carpetas
__pycache__ creadas dentro de kernel/ y tests/ durante la ejecución de tests.
"""
from __future__ import annotations

import atexit
import shutil
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

def _remove_pycache_dirs() -> None:
    """Elimina las cachés Python generadas dentro del repositorio."""
    for root in (_REPO_ROOT / "kernel", _REPO_ROOT / "tests"):
        if not root.exists():
            continue

        for pycache in root.rglob("__pycache__"):
            if pycache.is_dir() and not pycache.is_symlink():
                shutil.rmtree(pycache, ignore_errors=True)

atexit.register(_remove_pycache_dirs)

# API pública del paquete Kernel.
from .execution_order import ExecutionOrder, resolve_execution

__all__ = ["ExecutionOrder", "resolve_execution"]

#!/usr/bin/env python3
"""Compatibility wrapper for the Code Index runtime manifest."""
from __future__ import annotations

import importlib
import os

_impl = importlib.import_module("core_impl")


def _runtime_manifest_path(_root: str) -> str:
    """Keep the SQLite manifest in the repository's code-index directory."""
    manifest = os.environ.get("TONY_INDEX_MANIFEST")
    if manifest:
        manifest = os.path.abspath(os.path.expanduser(manifest))
    else:
        manifest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.db")
    os.makedirs(os.path.dirname(manifest), exist_ok=True)
    return manifest


_impl.manifest_path = _runtime_manifest_path

for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)


if __name__ == "__main__":
    _impl._cli()

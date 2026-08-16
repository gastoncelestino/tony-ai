#!/usr/bin/env python3
"""Compatibility wrapper that keeps Code Index runtime state outside the repo."""
from __future__ import annotations

import importlib
import os

_impl = importlib.import_module("core_impl")


def _runtime_manifest_path(_root: str) -> str:
    runtime_root = os.environ.get("TONY_RUNTIME_DIR")
    if runtime_root:
        runtime_root = os.path.abspath(os.path.expanduser(runtime_root))
    else:
        repo_root = os.environ.get("TONY_REPO_ROOT") or os.getcwd()
        project = os.path.basename(os.path.abspath(repo_root)) or "default"
        runtime_root = os.path.join(os.path.expanduser("~"), ".tony-ai", project)
    directory = os.path.join(runtime_root, "code-index", ".codeindex")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, "manifest.db")


_impl.manifest_path = _runtime_manifest_path

for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)


if __name__ == "__main__":
    _impl._cli()

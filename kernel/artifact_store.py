"""
Tony Kernel — Artifact Store

Real-store artifact verification for the phase gate.

Closes the "does the artifact really exist" gap: instead of trusting only the
in-memory ChangeState, the gate can ask a store whether the reported artifact
actually exists in the backend.

- openspec / hybrid / inline: the artifact is a real file; we verify the path
  resolves to a file on disk and (when a hash was recorded) that its content
  still matches the recorded sha256. A missing file or a content drift fails.
- tonymem: artifacts are topic-key observations in the memory SQLite DB, which
  lives in another process; the kernel has no direct handle, so this store
  does not second-guess the recorded reference.

Stdlib-only.
"""
from __future__ import annotations

import hashlib
import os
from typing import Callable, Optional

from .schemas import ArtifactRef


def _file_sha256(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def disk_artifact_store(base_dir: str = ".") -> Callable[[ArtifactRef], bool]:
    """Build a store that verifies artifacts against the local filesystem.

    ``base_dir`` is the project root that reported artifact paths are relative
    to. Only file-backed stores (openspec/hybrid/inline) are checked; tonymem
    references pass through.

    A reference passes only when the file exists, is readable, is non-empty,
    and (when a hash was recorded) its content still matches the recorded
    sha256.
    """

    def verify(art: ArtifactRef) -> bool:
        if art.store not in ("openspec", "hybrid", "inline"):
            return True
        if not art.path:
            return False
        full = os.path.join(base_dir, art.path.lstrip("/"))
        try:
            if not os.path.isfile(full):
                return False
            size = os.path.getsize(full)
            if size <= 0:
                return False
        except OSError:
            return False
        if art.hash:
            current = _file_sha256(full)
            if current is None or current != art.hash:
                return False
        return True

    return verify


def disk_artifact_hasher(base_dir: str = ".") -> Callable[[ArtifactRef], Optional[str]]:
    """Build a hasher that reports the CURRENT sha256 of a file-backed artifact.

    Used to make checksum verification read the truth from disk instead of
    trusting the hashes an agent reports.

    Return semantics:
    - ``None``  — not a file-backed store (tonymem): pass the reported hash through
    - ``""``    — file-backed but missing, unreadable, or empty (signal as gone)
    - else      — current sha256 of the file on disk
    """

    def current_hash(art: ArtifactRef) -> Optional[str]:
        if art.store not in ("openspec", "hybrid", "inline"):
            return None
        if not art.path:
            return ""
        full = os.path.join(base_dir, art.path.lstrip("/"))
        try:
            if not os.path.isfile(full) or os.path.getsize(full) <= 0:
                return ""
            return _file_sha256(full) or ""
        except OSError:
            return ""

    return current_hash

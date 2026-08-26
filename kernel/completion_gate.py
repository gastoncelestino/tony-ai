"""Minimal completion evidence gate."""
from __future__ import annotations


def validate_completion(evidence: object) -> bool:
    """Accept completion only when at least one piece of evidence is present."""
    return evidence is not None and bool(evidence)

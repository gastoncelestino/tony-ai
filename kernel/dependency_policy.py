"""Minimal Kernel-owned dependency readiness policy."""
from __future__ import annotations


def are_dependencies_satisfied(
    dependencies: tuple[str, ...] | list[str],
    satisfied: tuple[str, ...] | list[str],
) -> bool:
    """Return whether every declared dependency has been satisfied."""
    return all(dependency in satisfied for dependency in dependencies)

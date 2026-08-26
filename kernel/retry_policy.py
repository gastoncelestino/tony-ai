from __future__ import annotations


DEFAULT_MAX_ATTEMPTS = 3


def can_retry(attempts: int, max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> bool:
    """Return whether another execution attempt is permitted."""
    if attempts < 0:
        return False
    if max_attempts < 1:
        return False
    return attempts < max_attempts

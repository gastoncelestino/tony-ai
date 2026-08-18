"""Declarative allowlist for documentation sources available through Context7."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SOURCES_FILE = Path(__file__).with_name("sources.json")


def get_enabled_sources() -> list[dict[str, Any]]:
    """Return only sources explicitly enabled in the declarative allowlist."""
    with SOURCES_FILE.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return [source for source in data.get("sources", []) if source.get("enabled") is True]

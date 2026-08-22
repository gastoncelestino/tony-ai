"""Access the closed, declarative allowlist of documentation sources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SOURCES_FILE = Path(__file__).resolve().parents[1] / "config" / "knowledge_sources.json"


def get_enabled_sources() -> list[dict[str, Any]]:
    """Return only sources explicitly enabled by the project configuration."""
    with SOURCES_FILE.open(encoding="utf-8") as handle:
        data = json.load(handle)

    return [source for source in data.get("sources", []) if source.get("enabled") is True]

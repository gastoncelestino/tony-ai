from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup.sh"
OPENCODE = ROOT / "opencode.json"


CANONICAL_OMNICODER = "carstenuhlig/omnicoder-9b"


def test_setup_shell_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SETUP)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_setup_starts_only_missing_services() -> None:
    text = SETUP.read_text(encoding="utf-8")

    assert "SERVICES_TO_START=()" in text
    assert '[[ "${OLLAMA_UP}" -eq 0 ]] && SERVICES_TO_START+=(ollama)' in text
    assert '[[ "${QDRANT_UP}" -eq 0 ]] && SERVICES_TO_START+=(qdrant)' in text
    assert 'docker compose -f "${REPO_ROOT}/docker/docker-compose.yml" up -d "${SERVICES_TO_START[@]}"' in text


def test_setup_uses_canonical_omnicoder_model() -> None:
    text = SETUP.read_text(encoding="utf-8")

    assert CANONICAL_OMNICODER in text
    assert "omnicoder:9b" not in text


def test_opencode_uses_canonical_omnicoder_model() -> None:
    data = json.loads(OPENCODE.read_text(encoding="utf-8"))
    models = data["provider"]["ollama"]["models"]

    assert CANONICAL_OMNICODER in models
    assert "omnicoder:9b" not in models

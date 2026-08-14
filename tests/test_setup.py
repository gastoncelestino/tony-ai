from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup.sh"
OPENCODE = ROOT / "opencode.json"
ENV_EXAMPLE = ROOT / ".env.example"


CANONICAL_OMNICODER = "carstenuhlig/omnicoder-2-9b:q4_k_m"
LEGACY_OMNICODER = "omnicoder:9b"
PREVIOUS_OMNICODER = "carstenuhlig/omnicoder-9b"


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
    assert LEGACY_OMNICODER not in text
    assert PREVIOUS_OMNICODER not in text


def test_opencode_uses_canonical_omnicoder_model() -> None:
    data = json.loads(OPENCODE.read_text(encoding="utf-8"))
    models = data["provider"]["ollama"]["models"]

    assert CANONICAL_OMNICODER in models
    assert LEGACY_OMNICODER not in models
    assert PREVIOUS_OMNICODER not in models


def test_env_example_uses_canonical_omnicoder_model() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert f"TONY_IMPLEMENTATION_MODEL={CANONICAL_OMNICODER}" in text
    assert LEGACY_OMNICODER not in text
    assert PREVIOUS_OMNICODER not in text

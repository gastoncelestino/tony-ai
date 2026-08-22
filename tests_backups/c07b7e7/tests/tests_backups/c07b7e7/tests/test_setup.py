from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup.sh"
OPENCODE = ROOT / "opencode.json"
ENV_FILE = ROOT / ".env"
REQUIREMENTS = ROOT / "requirements-dev.txt"

CANONICAL_OMNICODER = "carstenuhlig/omnicoder-2-9b:q4_k_m"
LEGACY_OMNICODER = "omnicoder:9b"
PREVIOUS_OMNICODER = "carstenuhlig/omnicoder-9b"
MANDATORY_REQUIREMENTS = ("python3", "bun", "opencode", "docker", "ollama", "gga")


def test_setup_shell_syntax() -> None:
    result = subprocess.run(["bash", "-n", str(SETUP)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_setup_requires_all_tooling() -> None:
    text = SETUP.read_text(encoding="utf-8")
    for tool in MANDATORY_REQUIREMENTS:
        assert tool in text
    assert "DOCKER_AVAILABLE=0" in text
    assert 'bad "docker no esta instalado' in text
    assert 'bad "gga no esta en PATH' in text
    assert "import tree_sitter, tree_sitter_language_pack" in text
    assert "requirements-dev.txt fallo" in text
    assert "2>/dev/null" not in text.split('python3 -m pip install', 1)[1].split('hdr ".env"', 1)[0]


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


def test_tree_sitter_is_mandatory_and_default_chunker() -> None:
    setup = SETUP.read_text(encoding="utf-8")
    env = ENV_FILE.read_text(encoding="utf-8")
    requirements = REQUIREMENTS.read_text(encoding="utf-8")
    config = json.loads(OPENCODE.read_text(encoding="utf-8"))

    assert "tree-sitter" in requirements
    assert "tree-sitter-language-pack" in requirements
    assert "tree-sitter-languages" not in requirements
    assert "TONY_INDEX_CHUNKER=tree-sitter" in env
    assert 'TONY_INDEX_CHUNKER=tree-sitter' in setup
    assert config["mcp"]["code-index"]["environment"]["TONY_INDEX_CHUNKER"] == "tree-sitter"


def test_opencode_uses_canonical_omnicoder_model() -> None:
    data = json.loads(OPENCODE.read_text(encoding="utf-8"))
    models = data["provider"]["ollama"]["models"]
    assert CANONICAL_OMNICODER in models
    assert LEGACY_OMNICODER not in models
    assert PREVIOUS_OMNICODER not in models


def test_env_uses_canonical_omnicoder_model() -> None:
    text = ENV_FILE.read_text(encoding="utf-8")
    assert f"TONY_IMPLEMENTATION_MODEL={CANONICAL_OMNICODER}" in text
    assert LEGACY_OMNICODER not in text
    assert PREVIOUS_OMNICODER not in text


def test_install_docs_mark_prerequisites_mandatory() -> None:
    text = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
    for requirement in ("Python 3.10+", "Bun", "OpenCode CLI", "Ollama", "Docker", "GGA", "tree-sitter"):
        assert requirement in text
    assert "opcional" not in text.lower()
    assert "tree-sitter-languages" not in text
    assert "tree-sitter-language-pack" in text

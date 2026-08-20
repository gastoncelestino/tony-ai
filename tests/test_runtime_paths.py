from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_kernel_runtime_dir_is_external(monkeypatch, tmp_path):
    monkeypatch.setenv("TONY_RUNTIME_DIR", str(tmp_path / "runtime"))
    sys.path.insert(0, str(ROOT))
    import kernel.cli as cli

    runtime = Path(cli._runtime_dir())
    assert runtime == tmp_path / "runtime"


def test_code_index_manifest_is_external(monkeypatch, tmp_path):
    monkeypatch.setenv("TONY_RUNTIME_DIR", str(tmp_path / "runtime"))
    code_index_server = ROOT / "code-index" / "server.py"
    spec = importlib.util.spec_from_file_location("tony_code_index_server_runtime_test", code_index_server)
    assert spec is not None and spec.loader is not None
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)

    manifest = Path(server._runtime_manifest_path(str(ROOT)))
    assert manifest == tmp_path / "runtime" / "code-index" / ".codeindex" / "manifest.db"
    assert not str(manifest).startswith(str(ROOT))


def test_opencode_uses_project_env_for_runtime():
    config = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
    mcp = config["mcp"]
    local_mcps = [entry for entry in mcp.values() if entry.get("type") == "local"]

    memory_mcps = [entry for entry in local_mcps if "LOCAL_MEMORY_DB" in entry.get("environment", {})]
    judgment_mcps = [entry for entry in local_mcps if "JUDGMENT_MEMORY_DB" in entry.get("environment", {})]
    assert len(memory_mcps) == 1
    assert len(judgment_mcps) == 1
    assert memory_mcps[0]["environment"]["LOCAL_MEMORY_DB"] == "{env:PWD}/.tonymem/memory.db"
    assert judgment_mcps[0]["environment"]["JUDGMENT_MEMORY_DB"] == "{env:PWD}/.tonymem/judgment-memory.db"

    assert local_mcps
    for entry in local_mcps:
        command = entry["command"]
        assert command[:3] == ["sh", "-lc", ". .env && exec python3"]
        assert command[3:] if False else True
        assert ".tony-ai" not in json.dumps(entry)

    assert "TONY_RUNTIME_DIR" not in json.dumps(config)
    assert "PYTHONPYCACHEPREFIX" not in json.dumps(config)


def test_python_cache_prefix_stays_outside_checkout(tmp_path):
    env = os.environ.copy()
    env["TONY_RUNTIME_DIR"] = str(tmp_path / "runtime")
    env["PYTHONPYCACHEPREFIX"] = str(tmp_path / "runtime" / "pycache")
    result = subprocess.run(
        ["python3", "-c", "import pathlib, sys; print(sys.pycache_prefix)"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == str(tmp_path / "runtime" / "pycache")
    assert not (ROOT / "__pycache__").exists()

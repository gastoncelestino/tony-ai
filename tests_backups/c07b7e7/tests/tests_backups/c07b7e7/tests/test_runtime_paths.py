from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_kernel_runtime_dir_is_external():
    with tempfile.TemporaryDirectory(prefix="tony-runtime-test-") as tmp:
        runtime_dir = Path(tmp) / "runtime"
        env = os.environ.copy()
        env["TONY_RUNTIME_DIR"] = str(runtime_dir)
        result = subprocess.run(
            [sys.executable, "-c", "from kernel.cli import _runtime_dir; print(_runtime_dir())"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == str(runtime_dir)


def test_code_index_manifest_is_external():
    with tempfile.TemporaryDirectory(prefix="tony-runtime-test-") as tmp:
        runtime_dir = Path(tmp) / "runtime"
        env = os.environ.copy()
        env["TONY_RUNTIME_DIR"] = str(runtime_dir)
        code_index_server = ROOT / "code-index" / "server.py"
        spec = importlib.util.spec_from_file_location("tony_code_index_server_runtime_test", code_index_server)
        assert spec is not None and spec.loader is not None
        server = importlib.util.module_from_spec(spec)
        previous = os.environ.get("TONY_RUNTIME_DIR")
        os.environ["TONY_RUNTIME_DIR"] = str(runtime_dir)
        try:
            spec.loader.exec_module(server)
            manifest = Path(server._runtime_manifest_path(str(ROOT)))
        finally:
            if previous is None:
                os.environ.pop("TONY_RUNTIME_DIR", None)
            else:
                os.environ["TONY_RUNTIME_DIR"] = previous

        assert manifest == runtime_dir / "code-index" / ".codeindex" / "manifest.db"
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
        assert command[:2] == ["sh", "-lc"]
        assert command[2].startswith(". .env && exec python3 ")
        assert command[2].endswith("\"")
        script_path = command[2].split('python3 "', 1)[1][:-1]
        assert script_path.startswith("$PWD/")
        assert (ROOT / script_path.removeprefix("$PWD/")).is_file()
        assert ".tony-ai" not in json.dumps(entry)

    assert "TONY_RUNTIME_DIR" not in json.dumps(config)
    assert "PYTHONPYCACHEPREFIX" not in json.dumps(config)


def test_python_cache_prefix_stays_outside_checkout():
    with tempfile.TemporaryDirectory(prefix="tony-runtime-test-") as tmp:
        runtime_dir = Path(tmp) / "runtime"
        env = os.environ.copy()
        env["TONY_RUNTIME_DIR"] = str(runtime_dir)
        env["PYTHONPYCACHEPREFIX"] = str(runtime_dir / "pycache")
        result = subprocess.run(
            ["python3", "-c", "import pathlib, sys; print(sys.pycache_prefix)"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == str(runtime_dir / "pycache")
        assert not (ROOT / "__pycache__").exists()

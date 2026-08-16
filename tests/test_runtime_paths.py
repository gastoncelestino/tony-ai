from __future__ import annotations

import importlib.util
import json
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


def test_opencode_keeps_sqlite_and_moves_runtime():
    config = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
    mcp = config["mcp"]

    assert mcp["tonymem"]["environment"]["LOCAL_MEMORY_DB"] == "{env:PWD}/.tonymem/memory.db"
    assert mcp["judgment-memory"]["environment"]["JUDGMENT_MEMORY_DB"] == "{env:PWD}/.tonymem/judgment-memory.db"

    for name in ("tonymem", "code-index", "judgment-memory", "tony-kernel"):
        env = mcp[name]["environment"]
        assert env["TONY_RUNTIME_DIR"] == "{env:HOME}/.tony-ai/tony-ai"
        assert env["PYTHONPYCACHEPREFIX"] == "{env:HOME}/.tony-ai/tony-ai/pycache"

    assert "TONY_KERNEL_STATE_DIR" not in mcp["tony-kernel"]["environment"]

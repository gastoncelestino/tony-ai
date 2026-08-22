#!/usr/bin/env python3
"""Tony-AI Code Indexer — MCP server."""

import json
import os
import sys
from dataclasses import asdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core  # noqa: E402

PROJECT_ROOT = os.environ.get("TONY_INDEX_ROOT", os.getcwd())


def _extract_project_name(directory: str) -> str:
    import subprocess
    try:
        result = subprocess.run(["git", "-C", directory, "remote", "get-url", "origin"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            url = result.stdout.strip()
            name = url.rstrip("/").removesuffix(".git").split("/")[-1].split(":")[-1]
            if name:
                return name
    except Exception:
        pass
    try:
        result = subprocess.run(["git", "-C", directory, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return os.path.basename(result.stdout.strip())
    except Exception:
        pass
    return os.path.basename(os.path.abspath(directory)) or "default"


DEFAULT_PROJECT = _extract_project_name(PROJECT_ROOT)


def _runtime_manifest_path(_root: str) -> str:
    """Keep the incremental code-index SQLite manifest in code-index/."""
    manifest = os.environ.get("TONY_INDEX_MANIFEST")
    if manifest:
        manifest = os.path.abspath(os.path.expanduser(manifest))
    else:
        manifest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.db")
    os.makedirs(os.path.dirname(manifest), exist_ok=True)
    return manifest


core.manifest_path = _runtime_manifest_path


def code_search(args: dict) -> dict:
    results = core.search_code(args["query"], args.get("project", DEFAULT_PROJECT), limit=min(int(args.get("limit", 8)), 25), path_prefix=args.get("path_prefix"))
    return {"results": results, "count": len(results)}


def code_reindex(args: dict) -> dict:
    stats = core.index_repo(args.get("path", PROJECT_ROOT), args.get("project", DEFAULT_PROJECT))
    return asdict(stats)


def code_index_status(args: dict) -> dict:
    return core.index_status(args.get("path", PROJECT_ROOT), args.get("project", DEFAULT_PROJECT))


TOOLS = {
    "code_search": {"description": "Semantic search over the indexed codebase. Returns the most relevant code chunks.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "project": {"type": "string"}, "limit": {"type": "number"}, "path_prefix": {"type": "string"}}, "required": ["query"]}, "handler": code_search},
    "code_reindex": {"description": "Incrementally index or reindex the codebase. Unchanged files are skipped by content hash.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "project": {"type": "string"}}, "required": []}, "handler": code_reindex},
    "code_index_status": {"description": "Show code-index coverage and manifest status for the project.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "project": {"type": "string"}}, "required": []}, "handler": code_index_status},
}


def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(msg: dict):
    method = msg.get("method")
    msg_id = msg.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "code-index", "version": "1.0.0"}}}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [{"name": n, "description": t["description"], "inputSchema": t["inputSchema"]} for n, t in TOOLS.items()]}}
    if method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name")
        tool = TOOLS.get(tool_name)
        args = params.get("arguments", {}) or {}
        if not tool:
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"unknown tool: {tool_name}"}}
        try:
            result = tool["handler"](args)
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": f"error: {exc}"}], "isError": True}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if msg_id is not None:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"unknown method: {method}"}}
    return None


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(msg)
        if response is not None:
            send(response)


if __name__ == "__main__":
    main()

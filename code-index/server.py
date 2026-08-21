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
    "code_reindex": {"description": "Index or reindex the project codebase.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "project": {"type": "string"}}}, "handler": code_reindex},
    "code_index_status": {"description": "Show code-index status for a project.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "project": {"type": "string"}}}, "handler": code_index_status},
}


def main() -> None:
    for line in sys.stdin:
        try:
            req = json.loads(line)
            method = req.get("method")
            if method == "tools/list":
                result = {"tools": [{"name": n, "description": t["description"], "inputSchema": t["inputSchema"]} for n, t in TOOLS.items()]}
            elif method == "tools/call":
                params = req.get("params", {})
                name = params.get("name")
                tool = TOOLS.get(name)
                if not tool:
                    raise ValueError(f"Unknown tool: {name}")
                result = tool["handler"](params.get("arguments", {}))
            else:
                result = {"error": f"Unsupported method: {method}"}
            print(json.dumps({"jsonrpc": "2.0", "id": req.get("id"), "result": result}), flush=True)
        except Exception as exc:
            print(json.dumps({"jsonrpc": "2.0", "id": req.get("id") if isinstance(req, dict) else None, "error": {"code": -32000, "message": str(exc)}}), flush=True)


if __name__ == "__main__":
    main()

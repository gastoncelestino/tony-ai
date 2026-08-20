#!/usr/bin/env python3
"""
Tony-AI Code Indexer — MCP server.

Exposes the Code Indexer + Qdrant pipeline (core.py) as three MCP tools:
`code_search`, `code_reindex`, `code_index_status`. Same newline-delimited
JSON-RPC-over-stdio framing as `local-memory/server.py`, copy-pasted
deliberately rather than imported — these are two independent MCP servers
that may run as separate processes/tabs, and duplicating ~90 lines of
framing code is cheaper than coupling their lifecycles together.

`code_reindex` runs synchronously and can be slow on a first full index of
a large repo (it has to embed every chunk). For a large monorepo's *first*
index, run the CLI directly instead so it isn't blocking an agent turn:

    python3 core.py index --path /path/to/repo --project myproj

After that, `code_reindex` calls here are incremental (unchanged files are
skipped by content hash) and fast enough to call from an agent turn.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core  # noqa: E402

# ---------------------------------------------------------------------------
# Project resolution — same convention as TonyMem (git remote > git root >
# cwd basename), so `project` names line up across TonyMem and the code
# index without the agent having to pass it explicitly.
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.environ.get("TONY_INDEX_ROOT", os.getcwd())


def _extract_project_name(directory: str) -> str:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "-C", directory, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            url = result.stdout.strip()
            name = url.rstrip("/").removesuffix(".git").split("/")[-1].split(":")[-1]
            if name:
                return name
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["git", "-C", directory, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return os.path.basename(result.stdout.strip())
    except Exception:
        pass
    return os.path.basename(os.path.abspath(directory)) or "default"


DEFAULT_PROJECT = _extract_project_name(PROJECT_ROOT)


def _runtime_manifest_path(_root: str) -> str:
    """Keep the incremental code-index SQLite manifest out of the checkout."""
    runtime_root = os.environ.get("TONY_RUNTIME_DIR")
    if not runtime_root:
        raise RuntimeError("TONY_RUNTIME_DIR must be configured")
    runtime_root = os.path.abspath(os.path.expanduser(runtime_root))
    directory = os.path.join(runtime_root, "code-index", ".codeindex")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, "manifest.db")


# core.py is also used as a standalone library/CLI. The MCP server is the
# long-lived runtime entrypoint, so override its manifest location here while
# preserving core.py's public API and the existing SQLite schema.
core.manifest_path = _runtime_manifest_path


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def code_search(args: dict) -> dict:
    query = args["query"]
    project = args.get("project", DEFAULT_PROJECT)
    limit = min(int(args.get("limit", 8)), 25)
    path_prefix = args.get("path_prefix")
    results = core.search_code(query, project, limit=limit, path_prefix=path_prefix)
    return {"results": results, "count": len(results)}


def code_reindex(args: dict) -> dict:
    project = args.get("project", DEFAULT_PROJECT)
    path = args.get("path", PROJECT_ROOT)
    stats = core.index_repo(os.path.abspath(path), project)
    return stats.__dict__


def code_index_status(args: dict) -> dict:
    project = args.get("project", DEFAULT_PROJECT)
    path = args.get("path", PROJECT_ROOT)
    return core.index_status(os.path.abspath(path), project)


TOOLS = {
    "code_search": {
        "description": (
            "Semantic search over the indexed codebase (RAG over code, not full-text grep — finds "
            "conceptually related code even without exact keyword matches). Use for 'where is X handled', "
            "'find code similar to Y', or before implementing something that might already exist elsewhere "
            "in the repo. Requires the project to have been indexed first (code_reindex)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language or code-like description of what to find"},
                "project": {"type": "string", "description": f"Defaults to '{DEFAULT_PROJECT}' (detected from git remote)"},
                "limit": {"type": "number", "description": "Max results, default 8, max 25"},
                "path_prefix": {"type": "string", "description": "Optional: restrict results to paths starting with this prefix"},
            },
            "required": ["query"],
        },
        "handler": code_search,
    },
    "code_reindex": {
        "description": (
            "Incrementally (re)index the codebase for semantic search: unchanged files (by content hash) "
            "are skipped, changed/new files are chunked and embedded, deleted files are removed from the "
            "index. Safe to call repeatedly. First-time full index of a large repo can be slow — prefer "
            "running `python3 core.py index` directly for that instead of calling this tool."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "path": {"type": "string", "description": f"Defaults to {PROJECT_ROOT}"},
            },
            "required": [],
        },
        "handler": code_reindex,
    },
    "code_index_status": {
        "description": "Check whether the codebase is indexed, how many files/chunks, and the Qdrant collection name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": [],
        },
        "handler": code_index_status,
    },
}

# ---------------------------------------------------------------------------
# MCP JSON-RPC over stdio (newline-delimited JSON, no external deps)
# ---------------------------------------------------------------------------

def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(msg: dict):
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "code-index", "version": "1.0.0"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [
                    {"name": name, "description": t["description"], "inputSchema": t["inputSchema"]}
                    for name, t in TOOLS.items()
                ]
            },
        }

    if method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {}) or {}
        tool = TOOLS.get(tool_name)
        if not tool:
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"unknown tool: {tool_name}"}}
        try:
            result = tool["handler"](args)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]},
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": f"error: {exc}"}], "isError": True},
            }

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

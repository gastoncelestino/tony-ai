#!/usr/bin/env python3
"""Tony local developer tools for OpenCode 1.18.22."""
from __future__ import annotations
import fnmatch
import json
import os
import sys
from pathlib import Path

DEFAULT_IGNORES = {".git", ".hg", ".svn", "node_modules", "dist", "build", ".next", ".turbo", "coverage", "__pycache__", ".venv", "venv"}
DEFAULT_INCLUDE = ["**/*"]
MAX_FILES = 8
MAX_FILE_BYTES = 8 * 1024
MAX_TOTAL_BYTES = 16 * 1024


def json_result(value: object) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}


def json_error(message: str) -> dict:
    return {"isError": True, "content": [{"type": "text", "text": message}]}


def workspace() -> Path:
    return Path.cwd().resolve()


def inside_workspace(path: Path) -> bool:
    try:
        path.relative_to(workspace())
        return True
    except ValueError:
        return False


def safe_scope(directory: str) -> Path:
    raw = Path(directory)
    root = (raw if raw.is_absolute() else workspace() / raw).resolve()
    workspace_root = workspace()
    if not inside_workspace(root):
        raise ValueError("Scope must be inside the OpenCode workspace")
    if root == workspace_root:
        raise ValueError("Repository-root batch_read is forbidden; choose a narrow directory such as kernel or plugins")
    if not root.is_dir():
        raise ValueError(f"Scope is not a directory: {root}")
    return root


def ignored(path: Path, scope: Path) -> bool:
    try:
        relative = path.relative_to(scope)
    except ValueError:
        return True
    return any(part in DEFAULT_IGNORES for part in relative.parts)


def matches(relative: str, patterns: list[str]) -> bool:
    normalized = relative.replace(os.sep, "/")
    name = Path(normalized).name
    for pattern in patterns:
        pattern = pattern.replace(os.sep, "/")
        if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(name, pattern):
            return True
        if pattern.startswith("**/") and fnmatch.fnmatch(normalized, pattern[3:]):
            return True
    return False


def batch_read(args: dict) -> dict:
    directory = str(args.get("directory") or "")
    if not directory:
        raise ValueError("directory is required and must name a narrow repository scope")
    scope = safe_scope(directory)
    patterns = args.get("include") or DEFAULT_INCLUDE
    if isinstance(patterns, str):
        patterns = [patterns]
    if not isinstance(patterns, list) or not all(isinstance(item, str) and item for item in patterns):
        raise ValueError("include must be a non-empty string or array of strings")

    requested_files = max(int(args.get("max_files", MAX_FILES)), 1)
    requested_file_bytes = max(int(args.get("max_file_bytes", MAX_FILE_BYTES)), 1)
    requested_total_bytes = max(int(args.get("max_total_bytes", MAX_TOTAL_BYTES)), 1)
    max_files = min(requested_files, MAX_FILES)
    max_file_bytes = min(requested_file_bytes, MAX_FILE_BYTES)
    max_total_bytes = min(requested_total_bytes, MAX_TOTAL_BYTES)

    files: list[dict] = []
    total_bytes = 0
    skipped: list[dict] = []
    candidates = sorted((path for path in scope.rglob("*") if path.is_file() and not ignored(path, scope)), key=lambda path: str(path.relative_to(scope)))

    for path in candidates:
        relative = str(path.relative_to(scope)).replace(os.sep, "/")
        if not matches(relative, patterns):
            continue
        resolved = path.resolve()
        if not inside_workspace(resolved):
            skipped.append({"path": relative, "reason": "outside_workspace"})
            continue
        size = resolved.stat().st_size
        if len(files) >= max_files:
            skipped.append({"path": relative, "reason": "max_files"})
            continue
        if size > max_file_bytes:
            skipped.append({"path": relative, "reason": "max_file_bytes", "bytes": size})
            continue
        if total_bytes + size > max_total_bytes:
            skipped.append({"path": relative, "reason": "max_total_bytes", "bytes": size})
            continue
        try:
            content = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            skipped.append({"path": relative, "reason": "non_utf8"})
            continue
        except OSError as exc:
            skipped.append({"path": relative, "reason": f"read_error: {exc}"})
            continue
        files.append({"path": str(resolved), "relative_path": relative, "bytes": size, "content": content})
        total_bytes += size

    return {"operation": "batch_read", "scope": str(scope), "include": patterns, "count": len(files), "total_bytes": total_bytes, "truncated": bool(skipped), "files": files, "skipped": skipped}


TOOLS = [{
    "name": "batch_read",
    "description": "Read many source files in one call inside a narrow directory of the current OpenCode workspace. Repository-root batch reads are forbidden. Use a focused scope such as kernel or plugins. Hard limits: 8 files, 8 KiB per file, 16 KiB total.",
    "inputSchema": {
        "type": "object",
        "required": ["directory"],
        "properties": {
            "directory": {"type": "string", "description": "Narrow directory inside the workspace, for example kernel or plugins. The repository root is forbidden."},
            "include": {"type": "array", "items": {"type": "string"}, "description": "File patterns relative to directory, for example **/*.ts."},
            "max_files": {"type": "integer", "minimum": 1, "maximum": MAX_FILES, "default": MAX_FILES},
            "max_file_bytes": {"type": "integer", "minimum": 1, "maximum": MAX_FILE_BYTES, "default": MAX_FILE_BYTES},
            "max_total_bytes": {"type": "integer", "minimum": 1, "maximum": MAX_TOTAL_BYTES, "default": MAX_TOTAL_BYTES}
        }
    }
}]

DISPATCH = {"batch_read": batch_read}


def handle(request: dict) -> dict:
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "tony-tools", "version": "1.0.0"}}}
    if method in {"notifications/initialized", "ping"}:
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = DISPATCH.get(name)
        if not fn:
            return {"jsonrpc": "2.0", "id": request_id, "result": json_error(f"Unknown tool: {name}")}
        try:
            return {"jsonrpc": "2.0", "id": request_id, "result": json_result(fn(args))}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": request_id, "result": json_error(str(exc))}
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle(request)
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except Exception as exc:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()

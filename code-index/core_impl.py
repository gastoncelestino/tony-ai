#!/usr/bin/env python3
"""
Tony-AI Code Indexer — chunk the repo, embed via llama-server, store in Qdrant.

This is the "Code Indexer" + "Qdrant" nodes of the Context Pipeline, built as
one module because in practice they're one pipeline: nothing to embed
without chunking, nothing to search without a vector store. Zero
third-party Python dependencies — the embeddings server and Qdrant are both
talked to over their plain HTTP APIs via `urllib.request`, same stdlib-only
philosophy as `local-memory/server.py`.

Two ways to use this file:
  1. As a library, imported by `server.py` (the MCP tool wrapper).
  2. As a CLI, for the initial full index of a large repo where you don't
     want to do it through a chatty MCP round-trip:

       python3 core.py index --path . --project myproj
       python3 core.py search --query "vaccination MERGE upsert" --project myproj

Requires:
  - llama-server (via llama-swap) running locally with the embedding model
    declared in config.yaml (default: bge-m3), exposing the OpenAI-compatible
    /v1/embeddings endpoint — not a native /api/embed-style endpoint.
  - Qdrant running locally (default: http://localhost:6333)
  - tree-sitter and tree-sitter-language-pack for structural chunking
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Optional
from dataclasses import dataclass, field

try:
    from tree_sitter_language_pack import get_parser
except ImportError:  # pragma: no cover - optional dependency for tests without tree-sitter installed
    get_parser = None

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Points at llama-swap,
# which serves the embedding models (nomic-embed-text, bge-m3) declared in
# config.yaml the same way it serves chat models — same port as
# TONY_LLAMASWAP_URL. Kept as a distinct env var (TONY_EMBEDDINGS_URL, not
# renamed) so it can still be overridden independently if needed.
EMBEDDINGS_URL = os.environ.get("TONY_EMBEDDINGS_URL", "http://localhost:8080")
EMBED_MODEL = os.environ.get("TONY_EMBED_MODEL", "bge-m3")
QDRANT_URL = os.environ.get("TONY_QDRANT_URL", "http://localhost:6333")

EMBEDDINGS_HEALTH_TIMEOUT = float(os.environ.get("TONY_EMBEDDINGS_HEALTH_TIMEOUT", "3"))
EMBEDDINGS_HEALTH_TTL = float(os.environ.get("TONY_EMBEDDINGS_HEALTH_TTL", "5"))

# Tree-sitter is mandatory. The environment variable is retained as an
# explicit contract, but regex is no longer a supported chunker.
CHUNKER = os.environ.get("TONY_INDEX_CHUNKER", "tree-sitter").lower()
if CHUNKER != "tree-sitter":
    raise RuntimeError(
        "TONY_INDEX_CHUNKER must be 'tree-sitter'; regex chunking is not supported"
    )

MAX_CHUNK_LINES = int(os.environ.get("TONY_INDEX_MAX_CHUNK_LINES", "260"))
MIN_CHUNK_LINES = int(os.environ.get("TONY_INDEX_MIN_CHUNK_LINES", "8"))
CHUNK_OVERLAP_LINES = int(os.environ.get("TONY_INDEX_CHUNK_OVERLAP", "30"))
MAX_FILE_BYTES = int(os.environ.get("TONY_INDEX_MAX_FILE_BYTES", str(1_500_000)))

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".turbo", "target", ".idea", ".vscode",
    ".codeindex", ".tonymem", "vendor",
}

BOUNDARY_PATTERNS = {
    ".py": re.compile(r"^(def |class |async def )", re.M),
    ".ts": re.compile(r"^(export\s+)?(async\s+)?(function|class|interface|type)\s|^export const \w+\s*=", re.M),
    ".tsx": re.compile(r"^(export\s+)?(async\s+)?(function|class|interface|type)\s|^export const \w+\s*=", re.M),
    ".js": re.compile(r"^(export\s+)?(async\s+)?function\s|^(export\s+)?class\s|^const \w+\s*=\s*\(", re.M),
    ".jsx": re.compile(r"^(export\s+)?(async\s+)?function\s|^(export\s+)?class\s|^const \w+\s*=\s*\(", re.M),
    ".go": re.compile(r"^func "),
    ".sql": re.compile(
        r"^\s*(CREATE\s+OR\s+REPLACE|CREATE)\s+(PROCEDURE|FUNCTION|PACKAGE|PACKAGE\s+BODY|TRIGGER|VIEW)\b",
        re.I | re.M,
    ),
    ".pkb": re.compile(r"^\s*(PROCEDURE|FUNCTION)\s+\w+", re.I | re.M),
    ".pks": re.compile(r"^\s*(PROCEDURE|FUNCTION)\s+\w+", re.I | re.M),
    ".lua": re.compile(r"^(local\s+)?function\s", re.M),
    ".sh": re.compile(r"^[\w_]+\s*\(\)\s*\{|^function\s+\w+"),
    ".nix": re.compile(r"^\s{0,2}[\w-]+\s*=\s*\{?\s*$|^\s{0,2}[\w-]+\s*=\s*(rec\s*)?\{"),
}

TEXT_EXTENSIONS = set(BOUNDARY_PATTERNS) | {
    ".md", ".yaml", ".yml", ".json", ".toml", ".txt", ".cfg", ".ini", ".env",
    ".c", ".h", ".cpp", ".hpp", ".rs", ".rb", ".php", ".java", ".kt", ".swift",
}


@dataclass
class Chunk:
    path: str
    start_line: int
    end_line: int
    text: str
    lang: str


@dataclass
class IndexStats:
    files_scanned: int = 0
    files_skipped_unchanged: int = 0
    files_indexed: int = 0
    chunks_upserted: int = 0
    chunks_deleted: int = 0
    errors: list = field(default_factory=list)

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

TS_LANGUAGE_BY_EXT = {
    ".py": "python", ".ts": "typescript", ".tsx": "tsx",
    ".js": "javascript", ".jsx": "javascript", ".go": "go",
    ".rs": "rust", ".java": "java", ".c": "c", ".cpp": "cpp",
    ".h": "c", ".hpp": "cpp",
}


def _split_fixed(lines: list, ext: str) -> list:
    """Fixed-size windows used only for file types without a tree-sitter grammar."""
    chunks = []
    i = 0
    n = len(lines)
    if n <= MAX_CHUNK_LINES:
        return [(0, n - 1)]
    step = MAX_CHUNK_LINES - CHUNK_OVERLAP_LINES
    while i < n:
        end = min(i + MAX_CHUNK_LINES, n) - 1
        chunks.append((i, end))
        if end == n - 1:
            break
        i += step
    return chunks


def _chunk_treesitter(lines: list, ext: str) -> list:
    """Chunk using the modern tree-sitter-language-pack parser API."""
    if get_parser is None:
        raise RuntimeError(
            "tree-sitter chunking requires tree-sitter-language-pack. "
            "Install it with: pip install tree-sitter-language-pack"
        )
    lang_name = TS_LANGUAGE_BY_EXT.get(ext)
    if not lang_name:
        return _split_fixed(lines, ext)

    parser = get_parser(lang_name)
    content = "\n".join(lines)
    tree = parser.parse(content.encode("utf-8"))
    boundaries = []

    def walk(node):
        if node.type in (
            "function_definition", "method_definition", "class_definition",
            "function_declarator", "method_declarator", "class_declaration",
            "function_declaration", "function",
        ):
            boundaries.append((node.start_point[0], node.end_point[0]))
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    if not boundaries:
        return _split_fixed(lines, ext)

    boundaries.sort()
    ranges = []
    for start, end in boundaries:
        if ranges and start <= ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))
    if ranges and ranges[0][0] > 0:
        ranges.insert(0, (0, ranges[0][0] - 1))

    merged = []
    pending_start = None
    for start, end in ranges:
        if pending_start is not None:
            start = pending_start
            pending_start = None
        length = end - start + 1
        if length < MIN_CHUNK_LINES and (start, end) != ranges[-1]:
            pending_start = start
            continue
        if length > MAX_CHUNK_LINES:
            for sub_start, sub_end in _split_fixed(lines[start:end + 1], ext):
                merged.append((start + sub_start, start + sub_end))
        else:
            merged.append((start, end))
    if pending_start is not None:
        merged.append((pending_start, len(lines) - 1))
    return merged if merged else _split_fixed(lines, ext)


def chunk_lines(lines: list, ext: str, chunker: Optional[str] = None) -> list:
    """Return inclusive 0-indexed ranges using mandatory tree-sitter chunking."""
    n = len(lines)
    if n == 0:
        return []
    mode = (chunker or CHUNKER).lower()
    if mode != "tree-sitter":
        raise ValueError("Only tree-sitter chunking is supported")
    return _chunk_treesitter(lines, ext)


def chunk_file(path: str, content: str, chunker: Optional[str] = None) -> list:
    ext = os.path.splitext(path)[1]
    lines = content.split("\n")
    ranges = chunk_lines(lines, ext, chunker=chunker)
    chunks = []
    for start, end in ranges:
        text = "\n".join(lines[start:end + 1]).strip()
        if not text:
            continue
        chunks.append(Chunk(path=path, start_line=start + 1, end_line=end + 1, text=text, lang=ext.lstrip(".") or "text"))
    return chunks


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def iter_source_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            ext = os.path.splitext(fname)[1]
            if ext not in TEXT_EXTENSIONS:
                continue
            full = os.path.join(dirpath, fname)
            try:
                if os.path.getsize(full) > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield full


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def point_id(project: str, path: str, start_line: int) -> str:
    """Deterministic UUID so re-indexing the same chunk upserts, not duplicates."""
    key = f"{project}:{path}:{start_line}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


# ---------------------------------------------------------------------------
# Manifest (tracks per-file hash + emitted point ids, for incremental reindex)
# ---------------------------------------------------------------------------

def manifest_path(root: str) -> str:
    d = os.path.join(root, ".codeindex")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "manifest.db")


def manifest_connect(root: str) -> sqlite3.Connection:
    conn = sqlite3.connect(manifest_path(root))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            point_ids TEXT NOT NULL,
            indexed_at TEXT NOT NULL
        )
        """
    )
    return conn


# ---------------------------------------------------------------------------
# Embeddings client (llama-server/llama-swap, stdlib only)
# ---------------------------------------------------------------------------

_embeddings_health_at: dict = {}


def _ensure_embeddings_server_alive(base_url: str = EMBEDDINGS_URL) -> None:
    now = time.monotonic()
    if now - _embeddings_health_at.get(base_url, 0.0) < EMBEDDINGS_HEALTH_TTL:
        return
    try:
        req = urllib.request.Request(f"{base_url}/health", method="GET")
        with urllib.request.urlopen(req, timeout=EMBEDDINGS_HEALTH_TIMEOUT) as resp:
            resp.read()
        _embeddings_health_at[base_url] = now
    except urllib.error.HTTPError:
        _embeddings_health_at[base_url] = now
    except Exception as exc:
        raise RuntimeError(
            f"Could not reach llama-server/llama-swap at {base_url} (health check): {exc}. "
            f"Is llama-swap running with '{EMBED_MODEL}' declared in config.yaml?"
        ) from exc


def embed_texts(texts: list, model: str = EMBED_MODEL, base_url: str = EMBEDDINGS_URL) -> list:
    if not texts:
        return []
    _ensure_embeddings_server_alive(base_url)
    payload = json.dumps({"model": model, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/v1/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach llama-server/llama-swap at {base_url} for embeddings (model={model}): {exc}. "
            f"Is llama-swap running with '{model}' declared in config.yaml?"
        ) from exc
    # OpenAI-compatible response shape: {"data": [{"embedding": [...], "index": 0}, ...]}
    data = body.get("data")
    if not data:
        raise RuntimeError(f"llama-server returned no embeddings for model={model}: {body}")
    ordered = sorted(data, key=lambda item: item.get("index", 0))
    embeddings = [item["embedding"] for item in ordered]
    return embeddings


def embedding_dim(model: str = EMBED_MODEL, base_url: str = EMBEDDINGS_URL) -> int:
    vecs = embed_texts(["dimension probe"], model=model, base_url=base_url)
    return len(vecs[0])


# ---------------------------------------------------------------------------
# Qdrant REST client (stdlib only)
# ---------------------------------------------------------------------------

def _qdrant_request(method: str, path: str, body: dict = None, base_url: str = QDRANT_URL) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Qdrant {method} {path} failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach Qdrant at {base_url}{path}: {exc}. Is Qdrant running? "
            f"(docker run -p 6333:6333 qdrant/qdrant)"
        ) from exc


def qdrant_ensure_collection(collection: str, dim: int, base_url: str = QDRANT_URL) -> None:
    try:
        _qdrant_request("GET", f"/collections/{collection}", base_url=base_url)
        return
    except RuntimeError:
        pass
    _qdrant_request(
        "PUT",
        f"/collections/{collection}",
        {"vectors": {"size": dim, "distance": "Cosine"}},
        base_url=base_url,
    )


def qdrant_upsert(collection: str, points: list, base_url: str = QDRANT_URL) -> None:
    if not points:
        return
    _qdrant_request(
        "PUT",
        f"/collections/{collection}/points?wait=true",
        {"points": points},
        base_url=base_url,
    )


def qdrant_delete(collection: str, ids: list, base_url: str = QDRANT_URL) -> None:
    if not ids:
        return
    _qdrant_request(
        "POST",
        f"/collections/{collection}/points/delete?wait=true",
        {"points": ids},
        base_url=base_url,
    )


def qdrant_search(collection: str, vector: list, limit: int = 8, path_prefix: str = None, base_url: str = QDRANT_URL) -> list:
    body = {"vector": vector, "limit": limit, "with_payload": True}
    if path_prefix:
        body["filter"] = {"must": [{"key": "path", "match": {"text": path_prefix}}]}
    result = _qdrant_request("POST", f"/collections/{collection}/points/search", body, base_url=base_url)
    return result.get("result", [])


def collection_name(project: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "-", project)
    return f"codeidx_{safe}"


# ---------------------------------------------------------------------------
# Index / reindex
# ---------------------------------------------------------------------------

def index_repo(root: str, project: str, embed_batch_size: int = 32,
               base_url_qdrant: str = QDRANT_URL,
               base_url_embeddings: str = EMBEDDINGS_URL,
               embed_model: str = EMBED_MODEL,
               chunker: Optional[str] = None) -> IndexStats:
    stats = IndexStats()
    manifest = manifest_connect(root)
    dim = embedding_dim(model=embed_model, base_url=base_url_embeddings)
    coll = collection_name(project)
    qdrant_ensure_collection(coll, dim, base_url=base_url_qdrant)
    seen_paths = set()

    for full_path in iter_source_files(root):
        rel_path = os.path.relpath(full_path, root)
        seen_paths.add(rel_path)
        stats.files_scanned += 1
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError as exc:
            stats.errors.append(f"{rel_path}: read error: {exc}")
            continue

        h = content_hash(content)
        row = manifest.execute("SELECT content_hash, point_ids FROM files WHERE path=?", (rel_path,)).fetchone()
        if row and row["content_hash"] == h:
            stats.files_skipped_unchanged += 1
            continue

        chunks = chunk_file(rel_path, content, chunker=chunker)
        if not chunks:
            continue

        try:
            vectors = embed_texts([c.text for c in chunks], model=embed_model, base_url=base_url_embeddings)
        except RuntimeError as exc:
            stats.errors.append(f"{rel_path}: {exc}")
            continue

        new_ids = []
        points = []
        for chunk, vec in zip(chunks, vectors):
            pid = point_id(project, rel_path, chunk.start_line)
            new_ids.append(pid)
            points.append({
                "id": pid,
                "vector": vec,
                "payload": {
                    "project": project,
                    "path": rel_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "lang": chunk.lang,
                    "text": chunk.text,
                },
            })

        if row:
            old_ids = json.loads(row["point_ids"])
            stale_ids = [i for i in old_ids if i not in new_ids]
            qdrant_delete(coll, stale_ids, base_url=base_url_qdrant)
            stats.chunks_deleted += len(stale_ids)

        qdrant_upsert(coll, points, base_url=base_url_qdrant)
        stats.chunks_upserted += len(points)
        stats.files_indexed += 1
        manifest.execute(
            "INSERT INTO files (path, content_hash, point_ids, indexed_at) VALUES (?,?,?,datetime('now')) "
            "ON CONFLICT(path) DO UPDATE SET content_hash=excluded.content_hash, point_ids=excluded.point_ids, indexed_at=excluded.indexed_at",
            (rel_path, h, json.dumps(new_ids)),
        )
        manifest.commit()

    all_known = manifest.execute("SELECT path, point_ids FROM files").fetchall()
    for r in all_known:
        if r["path"] not in seen_paths:
            ids = json.loads(r["point_ids"])
            qdrant_delete(coll, ids, base_url=base_url_qdrant)
            stats.chunks_deleted += len(ids)
            manifest.execute("DELETE FROM files WHERE path=?", (r["path"],))
    manifest.commit()
    manifest.close()
    return stats


def search_code(query: str, project: str, limit: int = 8, path_prefix: str = None,
                 base_url_qdrant: str = QDRANT_URL, base_url_embeddings: str = EMBEDDINGS_URL,
                 embed_model: str = EMBED_MODEL) -> list:
    coll = collection_name(project)
    vec = embed_texts([query], model=embed_model, base_url=base_url_embeddings)[0]
    hits = qdrant_search(coll, vec, limit=limit, path_prefix=path_prefix, base_url=base_url_qdrant)
    return [{
        "score": h["score"],
        "path": h["payload"]["path"],
        "start_line": h["payload"]["start_line"],
        "end_line": h["payload"]["end_line"],
        "lang": h["payload"]["lang"],
        "text": h["payload"]["text"],
    } for h in hits]


def index_status(root: str, project: str, base_url_qdrant: str = QDRANT_URL) -> dict:
    manifest = manifest_connect(root)
    row = manifest.execute("SELECT COUNT(*) AS n FROM files").fetchone()
    files_indexed = row["n"] if row else 0
    manifest.close()
    coll = collection_name(project)
    try:
        info = _qdrant_request("GET", f"/collections/{coll}", base_url=base_url_qdrant)
        points_count = info.get("result", {}).get("points_count")
        collection_exists = True
    except RuntimeError:
        points_count = None
        collection_exists = False
    return {
        "project": project,
        "collection": coll,
        "collection_exists": collection_exists,
        "files_indexed": files_indexed,
        "points_count": points_count,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    parser = argparse.ArgumentParser(description="Tony-AI code indexer (Code Indexer + Qdrant)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_index = sub.add_parser("index", help="Full/incremental index of a repo")
    p_index.add_argument("--path", default=".")
    p_index.add_argument("--project", required=True)
    p_index.add_argument(
        "--chunker", default=None, choices=["regex", "tree-sitter"],
        help="Chunker a usar; default $TONY_INDEX_CHUNKER (tree-sitter).",
    )

    p_search = sub.add_parser("search", help="Semantic search over an indexed repo")
    p_search.add_argument("--query", required=True)
    p_search.add_argument("--project", required=True)
    p_search.add_argument("--limit", type=int, default=8)
    p_search.add_argument("--path-prefix", default=None)

    p_status = sub.add_parser("status", help="Show index status for a project")
    p_status.add_argument("--path", default=".")
    p_status.add_argument("--project", required=True)

    args = parser.parse_args()

    if args.cmd == "index":
        stats = index_repo(os.path.abspath(args.path), args.project, chunker=args.chunker)
        print(json.dumps(stats.__dict__, indent=2, ensure_ascii=False))
    elif args.cmd == "search":
        results = search_code(args.query, args.project, limit=args.limit, path_prefix=args.path_prefix)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    elif args.cmd == "status":
        print(json.dumps(index_status(os.path.abspath(args.path), args.project), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _cli()

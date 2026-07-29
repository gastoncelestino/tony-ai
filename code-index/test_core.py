"""
Regression test for core.py's HTTP client logic (embed_texts / qdrant_*),
run against an in-process mock of Ollama's and Qdrant's REST APIs so this
doesn't depend on either service being up. Covers: full index, no-op
reindex, incremental update on file change, deletion cleanup, search, and
status.

Run with: python3 test_core.py
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(__file__))
import core

QDRANT_STATE = {"collections": {}}


def fake_vector(text: str, dim: int = 8) -> list:
    h = hashlib.sha256(text.encode()).digest()
    return [b / 255.0 for b in h[:dim]]


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = self._read_json()
        if self.path == "/api/embed":
            vecs = [fake_vector(t) for t in body["input"]]
            self._send(200, {"embeddings": vecs})
            return
        if self.path.endswith("/points?wait=true"):
            coll = self.path.split("/")[2]
            store = QDRANT_STATE["collections"].setdefault(coll, {})
            for p in body["points"]:
                store[p["id"]] = p
            self._send(200, {"result": {}})
            return
        if self.path.endswith("/points/delete?wait=true"):
            coll = self.path.split("/")[2]
            store = QDRANT_STATE["collections"].setdefault(coll, {})
            for pid in body["points"]:
                store.pop(pid, None)
            self._send(200, {"result": {}})
            return
        if self.path.endswith("/points/search"):
            coll = self.path.split("/")[2]
            store = QDRANT_STATE["collections"].get(coll, {})
            qv = body["vector"]
            def score(v):
                return sum(a*b for a, b in zip(qv, v))
            ranked = sorted(store.values(), key=lambda p: -score(p["vector"]))
            limit = body.get("limit", 8)
            prefix = None
            if body.get("filter"):
                prefix = body["filter"]["must"][0]["match"]["text"]
            results = []
            for p in ranked:
                if prefix and not p["payload"]["path"].startswith(prefix):
                    continue
                results.append({"score": score(p["vector"]), "payload": p["payload"]})
                if len(results) >= limit:
                    break
            self._send(200, {"result": results})
            return
        self._send(404, {"error": "unknown path " + self.path})

    def do_PUT(self):
        body = self._read_json()
        if self.path.endswith("/points?wait=true"):
            coll = self.path.split("/")[2]
            store = QDRANT_STATE["collections"].setdefault(coll, {})
            for p in body["points"]:
                store[p["id"]] = p
            self._send(200, {"result": {}})
            return
        coll = self.path.split("/")[-1]
        QDRANT_STATE["collections"].setdefault(coll, {})
        self._send(200, {"result": True})

    def do_GET(self):
        coll = self.path.split("/")[-1]
        if coll in QDRANT_STATE["collections"]:
            self._send(200, {"result": {"points_count": len(QDRANT_STATE["collections"][coll])}})
        else:
            self._send(404, {"status": {"error": "not found"}})


def run():
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmp, "sub"), exist_ok=True)
        with open(os.path.join(tmp, "a.py"), "w") as f:
            f.write("def foo():\n    return 1\n\n\ndef bar():\n    return 2\n")
        with open(os.path.join(tmp, "sub", "b.py"), "w") as f:
            f.write("class Baz:\n    def qux(self):\n        pass\n")

        print("--- first index ---")
        stats = core.index_repo(tmp, "demo", base_url_qdrant=base, base_url_ollama=base)
        print(stats.__dict__)
        assert stats.files_indexed == 2, stats.__dict__
        assert stats.errors == [], stats.errors

        print("--- reindex, no changes (should skip both) ---")
        stats2 = core.index_repo(tmp, "demo", base_url_qdrant=base, base_url_ollama=base)
        print(stats2.__dict__)
        assert stats2.files_skipped_unchanged == 2, stats2.__dict__
        assert stats2.files_indexed == 0

        print("--- modify a.py, reindex (should update only a.py, delete stale chunk ids) ---")
        with open(os.path.join(tmp, "a.py"), "w") as f:
            f.write("def foo():\n    return 1\n\n\ndef bar():\n    return 2\n\n\ndef new_one():\n    return 3\n")
        stats3 = core.index_repo(tmp, "demo", base_url_qdrant=base, base_url_ollama=base)
        print(stats3.__dict__)
        assert stats3.files_indexed == 1
        assert stats3.files_skipped_unchanged == 1

        print("--- delete b.py, reindex (should drop its points from qdrant+manifest) ---")
        os.remove(os.path.join(tmp, "sub", "b.py"))
        stats4 = core.index_repo(tmp, "demo", base_url_qdrant=base, base_url_ollama=base)
        print(stats4.__dict__)
        assert stats4.chunks_deleted >= 1

        print("--- search ---")
        results = core.search_code("new_one", "demo", limit=3, base_url_qdrant=base, base_url_ollama=base)
        print(json.dumps(results, indent=2))
        assert any("new_one" in r["text"] for r in results)

        print("--- status ---")
        status = core.index_status(tmp, "demo", base_url_qdrant=base)
        print(status)
        assert status["collection_exists"] is True
        assert status["files_indexed"] == 1  # only a.py left after b.py deletion

        print("\nALL ASSERTIONS PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run()

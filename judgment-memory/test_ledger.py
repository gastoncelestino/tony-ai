"""
Regression test for judgment-memory/ledger.py's full pipeline (Decision ->
Normalize -> Embedding -> Qdrant -> Recall), run against an in-process mock
of Ollama's and Qdrant's REST APIs so this doesn't depend on either service
being up — same approach as code-index/test_core.py.

Covers: SQLite-only path (no network), full index + recall happy path,
upsert-not-duplicate on re-recording the same execution_id, stats
aggregation across multiple records, and graceful degradation when
Qdrant/Ollama are unreachable (points at a closed port instead of a mock).

Run with: python3 test_ledger.py
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
import ledger


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
        if self.path.endswith("/points/search"):
            coll = self.path.split("/")[2]
            store = QDRANT_STATE["collections"].get(coll, {})
            qv = body["vector"]

            def score(v):
                return sum(a * b for a, b in zip(qv, v))

            ranked = sorted(store.values(), key=lambda p: -score(p["vector"]))
            limit = body.get("limit", 5)
            results = [{"id": p["id"], "score": score(p["vector"]), "payload": p["payload"]} for p in ranked[:limit]]
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


RECORD_A = {
    "execution_id": "jd-001",
    "project": "demo",
    "task": "optimize query",
    "judge_a": {"model": "qwen3", "decision": "approve"},
    "judge_b": {"model": "deepseek", "decision": "reject"},
    "agreement": "contradiction",
    "confidence": 0.91,
    "final": "reject",
    "fix": "added index",
    "lesson": "check execution plan before optimization",
}

RECORD_B = {
    "execution_id": "jd-002",
    "project": "demo",
    "task": "refactor API",
    "judge_a": {"model": "qwen3", "decision": "approve"},
    "judge_b": {"model": "qwen3-coder", "decision": "approve"},
    "agreement": "confirmed",
    "confidence": 0.98,
    "final": "approve",
    "fix": None,
    "lesson": "missing validation layer",
}


def run():
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    tmp = tempfile.mkdtemp()
    ledger.DB_PATH = os.path.join(tmp, "judgment-memory.db")
    try:
        ledger.init_db()

        # ── 1. SQLite-only path (no --index) ──────────────────────────────
        print("--- ledger-only save (no indexing) ---")
        result = ledger.save_judgment(RECORD_A)
        print(result)
        assert result["action"] == "created", result

        hist = ledger.history(project="demo")
        assert len(hist) == 1, hist
        assert hist[0]["execution_id"] == "jd-001"
        assert hist[0]["agreement"] == "contradiction"

        # ── 2. Full pipeline: index + record_judgment ──────────────────────
        print("--- full pipeline: record_judgment (embed + qdrant upsert) ---")
        result2 = ledger.record_judgment(RECORD_A, ollama_url=base, qdrant_url=base)
        print(result2)
        assert result2["indexed"] is True, result2
        assert result2["action"] == "updated"  # already existed from step 1

        result3 = ledger.record_judgment(RECORD_B, ollama_url=base, qdrant_url=base)
        assert result3["indexed"] is True, result3
        assert result3["action"] == "created"

        # ── 3. Re-recording the same execution_id upserts, doesn't duplicate ──
        print("--- re-recording jd-001 should update, not duplicate ---")
        RECORD_A_UPDATED = {**RECORD_A, "fix": "added composite index"}
        result4 = ledger.record_judgment(RECORD_A_UPDATED, ollama_url=base, qdrant_url=base)
        assert result4["action"] == "updated", result4
        hist2 = ledger.history(project="demo")
        assert len(hist2) == 2, f"expected 2 rows (jd-001, jd-002), got {len(hist2)}"
        jd001 = next(r for r in hist2 if r["execution_id"] == "jd-001")
        assert jd001["fix"] == "added composite index", jd001

        # ── 4. Semantic recall ──────────────────────────────────────────────
        print("--- recall: semantic search for a similar task ---")
        recall_result = ledger.recall("speed up a slow query", project="demo", ollama_url=base, qdrant_url=base)
        print(json.dumps(recall_result, indent=2))
        assert recall_result["available"] is True, recall_result
        assert len(recall_result["results"]) == 2, recall_result
        # deterministic fake_vector means exact-text match scores highest —
        # confirm the API shape is right rather than asserting exact ranking
        execution_ids = {r["execution_id"] for r in recall_result["results"]}
        assert execution_ids == {"jd-001", "jd-002"}, execution_ids

        # ── 5. Stats aggregation ────────────────────────────────────────────
        print("--- stats ---")
        stats = ledger.stats(project="demo")
        print(json.dumps(stats, indent=2))
        assert stats["total_judgments"] == 2, stats
        assert stats["by_final"] == {"reject": 1, "approve": 1}, stats
        assert stats["by_agreement"] == {"contradiction": 1, "confirmed": 1}, stats
        assert stats["contradiction_rate"] == 0.5, stats

        # ── 6. Validation ────────────────────────────────────────────────────
        print("--- validation: bad `final` value is rejected ---")
        try:
            ledger.save_judgment({**RECORD_A, "execution_id": "jd-003", "final": "maybe"})
            raise AssertionError("expected ValueError for invalid final")
        except ValueError:
            pass

        # ── 7. Graceful degradation when Qdrant/Ollama are unreachable ────
        print("--- degradation: unreachable qdrant/ollama ---")
        dead_url = "http://127.0.0.1:1"  # nothing listens here
        result5 = ledger.record_judgment(
            {**RECORD_A, "execution_id": "jd-004"}, ollama_url=dead_url, qdrant_url=dead_url
        )
        print(result5)
        assert result5["indexed"] is False, result5
        assert "index_error" in result5, result5
        # ledger write still happened despite the network failure
        assert any(r["execution_id"] == "jd-004" for r in ledger.history(project="demo", limit=10))

        recall_dead = ledger.recall("anything", project="demo", ollama_url=dead_url, qdrant_url=dead_url)
        assert recall_dead["available"] is False, recall_dead
        assert recall_dead["results"] == []

        print("\nALL ASSERTIONS PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        server.shutdown()


if __name__ == "__main__":
    run()

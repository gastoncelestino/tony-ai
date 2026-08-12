"""
Regression test for local-memory/server.py (TonyMem MCP server).

This was the only untested subsystem in the repo — a pure-stdlib SQLite
memory server whose tools the whole orchestration layer calls by name.
Tests run against a throwaway DB file (LOCAL_MEMORY_DB) so they never touch
a real memory.db, and exercise the JSON-RPC framing plus every tool.

Highlights:
  - UPSERT semantics: same (project, topic_key) updates in place, never
    duplicates; NULL topic_key always creates.
  - Concurrency: N threads saving the same topic_key must not crash (the
    race that used to end in UNIQUE constraint failed) and must leave one
    row.
  - FTS search defaults: 'all' vs 'any' match modes, project/type filters,
    prompt-capture kept out of default results.
  - MCP framing: initialize, tools/list, unknown tool, error propagation.

Run with: pytest tests/test_local_memory_server.py  (or: python3 tests/test_local_memory_server.py)
"""

import os
import shutil
import sys
import tempfile
import threading

# Point the server at a throwaway DB BEFORE importing it (DB_PATH is read
# from the env at module import time).
_TMP = tempfile.mkdtemp()
os.environ["LOCAL_MEMORY_DB"] = os.path.join(_TMP, "memory-test.db")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "local-memory"))
import server  # noqa: E402


def count_rows(conn, where="", params=()):
    cur = conn.execute(f"SELECT COUNT(*) AS n FROM observations {where}", params)
    return cur.fetchone()["n"]


def test_local_memory_server():
    server.init_db()
    try:
        # ── 1. mem_save: create + upsert with topic_key ──────────────────
        print("--- mem_save: create + upsert semantics ---")
        r1 = server.mem_save({"title": "Auth design", "content": "JWT first version", "topic_key": "auth-model", "project": "demo", "type": "decision"})
        assert r1["action"] == "created", r1
        assert r1["topic_key"] == "auth-model"
        id1 = r1["id"]

        r2 = server.mem_save({"title": "Auth design v2", "content": "Switch to opaque tokens", "topic_key": "auth-model", "project": "demo", "type": "decision"})
        assert r2["action"] == "updated", r2
        assert r2["id"] == id1, (r2, id1)  # same row, no duplicate

        full = server.mem_get_observation({"id": id1})
        assert full["title"] == "Auth design v2", full
        assert full["content"] == "Switch to opaque tokens", full

        conn = server.connect()
        assert count_rows(conn, "WHERE project='demo'") == 1
        conn.close()

        # ── 2. mem_save without topic_key always creates ──────────────────
        print("--- mem_save: no topic_key -> always new rows ---")
        a = server.mem_save({"title": "X", "content": "one", "project": "demo"})
        b = server.mem_save({"title": "X", "content": "two", "project": "demo"})
        assert a["action"] == "created" and b["action"] == "created"
        assert a["id"] != b["id"]

        # ── 3. mem_save scopes are project-isolated ───────────────────────
        print("--- mem_save: project isolation ---")
        server.mem_save({"title": "Auth", "content": "scoped elsewhere", "topic_key": "auth-model", "project": "other"})
        conn = server.connect()
        assert count_rows(conn, "WHERE project='demo' AND topic_key='auth-model'") == 1
        conn.close()

        # ── 4. Concurrency: the race that used to crash ────────────────────
        print("--- concurrency: 8 threads saving the same topic_key ---")
        errors = []

        def worker(i):
            try:
                server.mem_save({"title": f"t{i}", "content": f"c{i}", "topic_key": "race-key", "project": "race"})
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, f"concurrent saves crashed: {errors}"
        conn = server.connect()
        assert count_rows(conn, "WHERE project='race' AND topic_key='race-key'") == 1
        conn.close()

        # ── 5. mem_search: FTS hit, filters, match modes ──────────────────
        print("--- mem_search: basic + filters ---")
        server.mem_save({"title": "JWT middleware", "content": "verify tokens on every request", "topic_key": "jwt-mw", "project": "demo", "type": "bugfix"})
        server.mem_save({"title": "Cache layer", "content": "tokens cached in redis with ttl", "project": "demo"})

        res = server.mem_search({"query": "verify tokens", "project": "demo"})
        assert len(res["results"]) >= 1, res
        assert any("JWT" in r["title"] for r in res["results"]), res

        # project filter excludes 'other'
        res = server.mem_search({"query": "auth", "project": "demo"})
        assert all(r["project"] == "demo" for r in res["results"]), res

        # type filter
        res = server.mem_search({"query": "tokens", "project": "demo", "type": "bugfix"})
        assert all(r["type"] == "bugfix" for r in res["results"]), res

        # match_mode 'any' returns more than 'all' for partial terms
        all_res = server.mem_search({"query": "verify ttl", "project": "demo"})
        any_res = server.mem_search({"query": "verify ttl", "project": "demo", "match_mode": "any"})
        assert len(any_res["results"]) >= len(all_res["results"]), (any_res, all_res)

        # limit capped at 20
        for i in range(25):
            server.mem_save({"title": f"noise {i}", "content": f"filler content {i}", "project": "demo"})
        res = server.mem_search({"query": "filler", "project": "demo", "limit": 999})
        assert len(res["results"]) <= 20, res

        # ── 6. mem_get_observation: missing id ────────────────────────────
        print("--- mem_get_observation: not found ---")
        missing = server.mem_get_observation({"id": 999999})
        assert "error" in missing, missing

        # ── 7. mem_update ─────────────────────────────────────────────────
        print("--- mem_update ---")
        upd = server.mem_update({"id": id1, "title": "Auth design v3", "content": "Signed JWTs, rotation"})
        assert upd["action"] == "updated", upd
        full = server.mem_get_observation({"id": id1})
        assert full["title"] == "Auth design v3", full

        err = server.mem_update({"id": 999999, "title": "nope"})
        assert "error" in err, err
        err2 = server.mem_update({"id": id1})
        assert "error" in err2, err2  # nothing to update

        # ── 8. mem_context: session summary first, no prompt-capture ──────
        print("--- mem_context ---")
        server.mem_session_summary({"content": "Session summary here", "project": "demo", "session_id": "s1"})
        ctx = server.mem_context({"project": "demo", "limit": 5})
        assert len(ctx["context"]) >= 1, ctx
        assert ctx["context"][0]["type"] == "session-summary", ctx  # summary is newest
        assert all(r["type"] != "prompt-capture" for r in ctx["context"]), ctx

        # ── 9. mem_session_summary upserts per session_id ─────────────────
        print("--- mem_session_summary: upsert per session ---")
        server.mem_session_summary({"content": "v1", "project": "demo", "session_id": "sx"})
        server.mem_session_summary({"content": "v2", "project": "demo", "session_id": "sx"})
        server.mem_session_summary({"content": "other", "project": "demo", "session_id": "sy"})
        conn = server.connect()
        assert count_rows(conn, "WHERE project='demo' AND type='session-summary'") == 3, "two sessions -> two rows"
        conn.close()

        # ── 10. mem_suggest_topic_key: collision-free slugs ───────────────
        print("--- mem_suggest_topic_key ---")
        first = server.mem_suggest_topic_key({"title": "Fix Auth Bug!", "project": "demo"})
        assert first["topic_key"] == "fix-auth-bug" and first["collision"] is False, first
        server.mem_save({"title": "x", "content": "y", "topic_key": "fix-auth-bug", "project": "demo"})
        second = server.mem_suggest_topic_key({"title": "Fix Auth Bug", "project": "demo"})
        assert second["topic_key"] == "fix-auth-bug-2" and second["collision"] is True, second

        # ── 11. mem_save_prompt stays out of default search ───────────────
        print("--- mem_save_prompt: internal, excluded from default search ---")
        server.mem_save_prompt({"content": "user asked about X", "project": "demo", "session_id": "s1"})
        res = server.mem_search({"query": "asked about", "project": "demo"})
        assert all(r["type"] != "prompt-capture" for r in res["results"]), res
        res = server.mem_search({"query": "asked about", "project": "demo", "type": "prompt-capture"})
        assert len(res["results"]) >= 1, res  # visible only when explicitly asked

        # ── 12. mem_review: lifecycle (mark_stale → list → mark_reviewed) ────
        print("--- mem_review: lifecycle ---")
        # default lifecycle_status is active
        row = server.mem_get_observation({"id": id1})
        assert row.get("lifecycle_status") == "active", row

        # list returns empty when nothing is stale
        stale = server.mem_review({"action": "list", "project": "demo"})
        assert stale["count"] == 0, stale

        # mark_stale moves it to needs_review via tool (no SQL direct)
        updated = server.mem_review({"action": "mark_stale", "ids": [id1]})
        assert updated["updated"] == 1, updated
        row = server.mem_get_observation({"id": id1})
        assert row["lifecycle_status"] == "needs_review", row

        # list now returns it
        stale = server.mem_review({"action": "list", "project": "demo"})
        assert stale["count"] == 1, stale
        assert stale["results"][0]["id"] == id1, stale

        # mark_reviewed moves it back to active
        updated = server.mem_review({"action": "mark_reviewed", "ids": [id1]})
        assert updated["updated"] == 1, updated
        stale = server.mem_review({"action": "list", "project": "demo"})
        assert stale["count"] == 0, stale

        # mark_reviewed with no ids errors
        err = server.mem_review({"action": "mark_reviewed"})
        assert "error" in err, err

        # mark_stale with no ids errors
        err = server.mem_review({"action": "mark_stale"})
        assert "error" in err, err

        # mem_search includes lifecycle_status in results (use mark_stale tool, not SQL)
        server.mem_review({"action": "mark_stale", "ids": [id1]})
        res = server.mem_search({"query": "Auth", "project": "demo"})
        match = next((r for r in res["results"] if r["id"] == id1), None)
        assert match is not None, res
        assert match["lifecycle_status"] == "needs_review", match

        # ── 13. mem_review: mark_proven + search ranking ──────────────────
        print("--- mem_review: proven + ranking ---")
        id2 = server.mem_save({"title": "Proven pattern", "content": "always use opaque tokens", "project": "demo", "type": "pattern"})["id"]

        # mark_proven sets lifecycle_status
        server.mem_review({"action": "mark_proven", "ids": [id2]})
        row = server.mem_get_observation({"id": id2})
        assert row["lifecycle_status"] == "proven", row

        # mem_search ranks proven first
        res = server.mem_search({"query": "tokens", "project": "demo"})
        assert len(res["results"]) >= 2, res
        first_id = res["results"][0]["id"]
        assert first_id == id2, f"proven should rank first, got {first_id}: {res['results']}"

        # list with status filter
        proven_list = server.mem_review({"action": "list", "project": "demo", "status": "proven"})
        assert proven_list["count"] == 1, proven_list
        assert proven_list["results"][0]["id"] == id2, proven_list

        # ── 14. mem_review: full cycle mark_stale → mark_reviewed → mark_proven
        print("--- mem_review: full cycle ---")
        id3 = server.mem_save({"title": "Cycle test", "content": "test full lifecycle", "project": "demo", "type": "pattern"})["id"]
        
        # active → stale
        server.mem_review({"action": "mark_stale", "ids": [id3]})
        assert server.mem_get_observation({"id": id3})["lifecycle_status"] == "needs_review"
        
        # stale → active
        server.mem_review({"action": "mark_reviewed", "ids": [id3]})
        assert server.mem_get_observation({"id": id3})["lifecycle_status"] == "active"
        
        # active → proven (direct, no guard)
        server.mem_review({"action": "mark_proven", "ids": [id3]})
        assert server.mem_get_observation({"id": id3})["lifecycle_status"] == "proven"
        
        # proven → stale (direct, no guard)
        server.mem_review({"action": "mark_stale", "ids": [id3]})
        assert server.mem_get_observation({"id": id3})["lifecycle_status"] == "needs_review"
        
        # stale → proven (direct, no guard)
        server.mem_review({"action": "mark_proven", "ids": [id3]})
        assert server.mem_get_observation({"id": id3})["lifecycle_status"] == "proven"

        # ── 15. MCP framing ───────────────────────────────────────────────
        print("--- MCP framing ---")
        init = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert init["result"]["protocolVersion"] == "2024-11-05", init
        assert init["result"]["serverInfo"]["name"] == "tonymem", init

        listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert len(listed["result"]["tools"]) == len(server.TOOLS), listed

        unknown = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope", "arguments": {}}})
        assert unknown["error"]["code"] == -32601, unknown

        # handler exception surfaces as isError, not a crash
        errored = server.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "mem_save", "arguments": {}}})
        assert errored["result"]["isError"] is True, errored
        assert "error:" in errored["result"]["content"][0]["text"], errored

        print("\nALL ASSERTIONS PASSED")
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    test_local_memory_server()

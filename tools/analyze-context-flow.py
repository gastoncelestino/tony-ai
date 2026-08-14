#!/usr/bin/env python3
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def load(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def pct(n, cap):
    return (n * 100 / cap) if cap else 0.0


def main():
    ap = argparse.ArgumentParser(description="Analyze Tony AI runtime context-flow traces")
    ap.add_argument("trace", nargs="?", default=".context-flow/runtime.jsonl")
    ap.add_argument("--context-limit", type=int, default=32768)
    args = ap.parse_args()

    rows = load(args.trace)
    if not rows:
        print(f"No trace events found in {args.trace}")
        print("Run OpenCode with TONY_CONTEXT_FLOW_TRACE=1 first.")
        return 2

    sessions = {}
    usage = []
    tool_after = []
    subtasks = []

    for r in rows:
        if r.get("event") in {"session.created", "session.updated"}:
            info = r.get("session") or {}
            if isinstance(info, dict) and info.get("id"):
                sessions[info["id"]] = info
        elif r.get("event") == "model.usage":
            usage.append(r)
        elif r.get("event") == "tool.after":
            tool_after.append(r)
        elif r.get("event") == "subtask.part":
            subtasks.append(r)

    print("\nTony AI — LIVE Context Flow Analysis")
    print("=====================================")
    print(f"Trace: {args.trace}")
    print(f"Events: {len(rows)}")
    print()

    print("MODEL USAGE")
    print("-----------")
    print(f"{'AGENT':<18} {'MODEL':<32} {'INPUT':>8} {'OUTPUT':>8} {'USE':>7} {'SESSION'}")
    print("-" * 105)
    for r in usage:
        inp = int(r.get("input_tokens") or 0)
        out = int(r.get("output_tokens") or 0)
        agent = str(r.get("agent") or "?")
        model = str(r.get("model") or "?")
        session = str(r.get("sessionID") or "?")
        print(f"{agent:<18} {model:<32} {inp:>8} {out:>8} {pct(inp,args.context_limit):>6.1f}% {session}")

    print()
    print("PHASE DELEGATIONS")
    print("-----------------")
    task_calls = [r for r in rows if r.get("event") == "tool.before" and r.get("tool") == "Task"]
    if not task_calls:
        print("No Task delegations captured.")
    for r in task_calls:
        print(f"{r.get('phase') or '?':<18} prompt+args={r.get('args_bytes',0):>7} B sha={str(r.get('args_sha256',''))[:12]}")

    print()
    print("TONYMEM RETRIEVAL")
    print("-----------------")
    mem = [r for r in tool_after if any(k in str(r.get("tool")) for k in ("mem_search", "mem_get_observation", "mem_save"))]
    if not mem:
        print("No TonyMem tool calls captured.")
    for r in mem:
        tool = str(r.get("tool"))
        print(f"{tool:<36} output={r.get('output_bytes',0):>8} B topic={r.get('topic_key') or '-'} query={r.get('query') or '-'}")

    print()
    print("ARTIFACT REUSE / DUPLICATION SIGNALS")
    print("-------------------------------------")
    by_sha = defaultdict(list)
    for r in mem:
        sha = r.get("output_sha256")
        if sha:
            by_sha[sha].append(r)
    repeated = [(sha, items) for sha, items in by_sha.items() if len(items) > 1]
    if not repeated:
        print("No repeated identical TonyMem payloads detected.")
    else:
        for sha, items in repeated:
            total = sum(int(x.get("output_bytes") or 0) for x in items)
            print(f"sha={sha[:12]} calls={len(items)} repeated_bytes={total}")
            for x in items:
                print(f"  - {x.get('tool')} topic={x.get('topic_key') or '-'} session={x.get('sessionID')}")

    print()
    print("INTERPRETATION")
    print("--------------")
    print("INPUT tokens come from OpenCode's real assistant message usage, not a prompt-size estimate.")
    print("TonyMem output sizes show what was actually returned by retrieval tools.")
    print("Repeated output hashes are a concrete duplication signal across retrieval calls.")
    print("This does not claim that every repeated payload is harmful duplication; compare it with the consuming phase and task prompt.")
    print()
    print("STATUS: live runtime trace analyzed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

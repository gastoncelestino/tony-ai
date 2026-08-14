#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required."
  exit 2
fi

python3 - <<'PY'
import json
import re
import subprocess
import sys
from pathlib import PurePosixPath

ROOT = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
PHASES = [
    "sdd-init", "sdd-onboard", "sdd-explore", "sdd-propose", "sdd-spec",
    "sdd-design", "sdd-tasks", "sdd-apply", "sdd-verify", "sdd-archive",
]
COMMON = "skills/_shared/sdd-phase-common.md"
BRANCHES = ["main", "dev"]

GREEN="\033[32m"
YELLOW="\033[33m"
RESET="\033[0m"


def git_show(branch, path):
    try:
        return subprocess.check_output(["git", "show", f"{branch}:{path}"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return None


def load_json(branch, path):
    raw = git_show(branch, path)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def resolve_ref(ref, source_path):
    ref = ref.strip()
    if ref.startswith("./"):
        base = PurePosixPath(source_path).parent
        return str((base / ref[2:]).as_posix())
    if ref.startswith("../"):
        base = PurePosixPath(source_path).parent
        return str((base / ref).as_posix())
    return ref


def collect_transitive(branch, path, seen, refs):
    if path in seen:
        return 0
    seen.add(path)
    content = git_show(branch, path)
    if content is None:
        return 0
    refs.append(path)
    total = len(content.encode("utf-8"))
    for raw_ref in re.findall(r"\{file:([^}]+)\}", content):
        child = resolve_ref(raw_ref, path)
        total += collect_transitive(branch, child, seen, refs)
    return total


def token_count(text):
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return enc.encode(text).__len__(), "tiktoken/cl100k_base"
    except Exception:
        return round(len(text.encode("utf-8")) / 4), "estimate chars/4"


def mcp_surface(branch, agent):
    cfg = load_json(branch, "opencode.json") or {}
    permissions = ((cfg.get("agent") or {}).get(agent) or {}).get("permission") or {}
    global_permissions = cfg.get("permission") or {}
    allowed = sorted(k for k, v in permissions.items() if v == "allow")
    denied_global = sorted(k for k, v in global_permissions.items() if v == "deny")
    return allowed, denied_global


def phase_prompt(branch, phase):
    cfg = load_json(branch, "opencode.json") or {}
    prompt_ref = (((cfg.get("agent") or {}).get(phase) or {}).get("prompt"))
    if isinstance(prompt_ref, str):
        m = re.fullmatch(r"\{file:(.+)\}", prompt_ref.strip())
        if m:
            return m.group(1).lstrip("./")
    return f"prompts/sdd/{phase}.md"


def fmt(n):
    return f"{n:,}".replace(",", ".")

print("\n=== Tony AI — Context Audit: main vs dev ===\n")
print("Context model: phase prompt + sdd-phase-common.md + transitive {file:...} references.")
print("MCP is reported separately as the allowed tool surface for each phase.")
print("Token count uses tiktoken/cl100k_base when installed; otherwise chars/4 is explicitly marked as an estimate.\n")

results = {b: {} for b in BRANCHES}
for branch in BRANCHES:
    print(f"--- {branch} ---")
    for phase in PHASES:
        prompt_path = phase_prompt(branch, phase)
        seen = set()
        refs = []
        prompt_bytes = collect_transitive(branch, prompt_path, seen, refs)
        common_bytes = collect_transitive(branch, COMMON, seen, refs)
        all_text = ""
        for p in refs:
            c = git_show(branch, p)
            if c:
                all_text += c + "\n"
        tokens, method = token_count(all_text)
        allowed, denied = mcp_surface(branch, phase)
        results[branch][phase] = {
            "bytes": prompt_bytes + common_bytes,
            "tokens": tokens,
            "method": method,
            "refs": refs,
            "mcp": allowed,
        }
        print(f"{phase:12} {fmt(prompt_bytes + common_bytes):>8} B | {fmt(tokens):>7} tok | refs={len(refs):>2} | MCP={', '.join(allowed) if allowed else 'none'}")
    print()

print("=== Comparison ===\n")
print(f"{'Phase':12} {'main tok':>10} {'dev tok':>10} {'saving':>9} {'main B':>10} {'dev B':>10} {'refs dev':>9}")
print("-" * 78)
for phase in PHASES:
    m = results["main"][phase]
    d = results["dev"][phase]
    saving = ((m["tokens"] - d["tokens"]) / m["tokens"] * 100) if m["tokens"] else 0
    print(f"{phase:12} {fmt(m['tokens']):>10} {fmt(d['tokens']):>10} {saving:>8.1f}% {fmt(m['bytes']):>10} {fmt(d['bytes']):>10} {len(d['refs']):>9}")

main_total = sum(results["main"][p]["tokens"] for p in PHASES)
dev_total = sum(results["dev"][p]["tokens"] for p in PHASES)
main_bytes = sum(results["main"][p]["bytes"] for p in PHASES)
dev_bytes = sum(results["dev"][p]["bytes"] for p in PHASES)
saving = ((main_total - dev_total) / main_total * 100) if main_total else 0
print("-" * 78)
print(f"{'TOTAL':12} {fmt(main_total):>10} {fmt(dev_total):>10} {saving:>8.1f}% {fmt(main_bytes):>10} {fmt(dev_bytes):>10}")

print("\n=== MCP surface ===\n")
for phase in PHASES:
    ma = results["main"][phase]["mcp"]
    da = results["dev"][phase]["mcp"]
    print(f"{phase:12} main=[{', '.join(ma) if ma else 'none'}]  dev=[{', '.join(da) if da else 'none'}]")

print("\n=== Dev loaded references ===\n")
for phase in PHASES:
    refs = results["dev"][phase]["refs"]
    print(f"{phase}: {', '.join(refs)}")

print("\nNOTE: this measures static prompt context only. Runtime-injected system messages, tool schemas, retrieved artifacts, memory results, and model-specific tokenization are not included.")
PY

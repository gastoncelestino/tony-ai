#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: Python 3 is required."
  exit 2
fi

python3 - <<'PY'
import json, math, os, re, subprocess, sys
from pathlib import Path

ROOT = Path.cwd()
PHASES = [
    "sdd-init", "sdd-onboard", "sdd-explore", "sdd-propose", "sdd-spec",
    "sdd-design", "sdd-tasks", "sdd-apply", "sdd-verify", "sdd-archive",
]
COMMON = "skills/_shared/sdd-phase-common.md"
ORCHESTRATOR = "prompts/agents/tony-orchestrator.md"
CONFIG = "opencode.json"

GREEN='\033[32m'; YELLOW='\033[33m'; RED='\033[31m'; RESET='\033[0m'

def git_show(path, ref="HEAD"):
    p = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return p.stdout if p.returncode == 0 else ""

def bytes_len(s):
    return len(s.encode("utf-8"))

def tokens(s):
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(s))
    except Exception:
        return math.ceil(bytes_len(s) / 4)

def pct(used, limit):
    return (used / limit * 100) if limit else 0

def level(used, limit):
    p = pct(used, limit)
    if p >= 90: return "CRITICAL"
    if p >= 75: return "HIGH"
    if p >= 50: return "WATCH"
    return "SAFE"

def refs_for(path, seen=None):
    seen = set() if seen is None else seen
    if path in seen: return []
    seen.add(path)
    text = git_show(path)
    out = [path] if text else []
    for raw in re.findall(r"\{file:([^}]+)\}", text):
        nested = raw
        if nested.startswith("./"):
            nested = str((Path(path).parent / nested[2:]).as_posix())
        out.extend(refs_for(nested, seen))
    return out

def prompt_context(path):
    parts = []
    for ref in refs_for(path):
        parts.append(git_show(ref))
    common = git_show(COMMON)
    if common: parts.append(common)
    return "\n".join(parts)

def model_limits(config):
    models = config.get("provider", {}).get("ollama", {}).get("models", {})
    result = {}
    for name, data in models.items():
        result[name] = int(data.get("limit", {}).get("context", data.get("options", {}).get("numCtx", 0)))
    return result

def phase_models(config):
    default = config.get("agent", {}).get("tony-orchestrator", {}).get("model", "unknown")
    out = {p: os.environ.get(f"TONY_MODEL_{p.upper().replace('-', '_')}", default) for p in PHASES}
    override = os.environ.get("TONY_PHASE_MODELS", "")
    for item in override.split(","):
        if "=" in item:
            p, m = item.split("=", 1)
            if p in PHASES: out[p] = m
    out["tony-orchestrator"] = os.environ.get("TONY_MODEL_ORCHESTRATOR", default)
    return out

def artifact_files():
    change = os.environ.get("SDD_CHANGE", "").strip()
    roots = []
    if change:
        roots += [ROOT / "openspec" / "changes" / change, ROOT / "changes" / change]
    files = []
    for root in roots:
        if root.is_dir():
            files.extend(p for p in root.rglob("*") if p.is_file())
    return sorted(set(files))

with open(ROOT / CONFIG, encoding="utf-8") as f:
    config = json.load(f)

limits = model_limits(config)
models = phase_models(config)
model_caps = {p: limits.get(m, 0) for p, m in models.items()}

print("\nTony AI — SDD Context Flow / Model Budget Test")
print("================================================")
print("Purpose: measure context carried by each actor and phase, then compare it with model context limits.")
print("Static prompt context includes transitive {file:...} references + common contract.")
change = os.environ.get("SDD_CHANGE", "")
print(f"Change artifacts: {change or 'not supplied (static flow only)'}")
print()

orch_text = git_show(ORCHESTRATOR)
orch_tokens = tokens(orch_text)
orch_bytes = bytes_len(orch_text)
orch_model = models["tony-orchestrator"]
orch_cap = limits.get(orch_model, 0)
print(f"ORCHESTRATOR  {orch_model}  {orch_bytes} B / {orch_tokens} tok  limit={orch_cap or 'unknown'}  {level(orch_tokens, orch_cap) if orch_cap else 'UNKNOWN'}")
print()

print(f"{'PHASE':<14} {'MODEL':<23} {'STATIC':>9} {'ARTIFACT':>10} {'TOTAL':>9} {'LIMIT':>9} {'USE':>7} STATUS")
print("-" * 96)

total_static = 0
artifact_total = sum(bytes_len(p.read_text(encoding="utf-8", errors="replace")) for p in artifact_files())
artifact_tok = sum(tokens(p.read_text(encoding="utf-8", errors="replace")) for p in artifact_files())

for phase in PHASES:
    text = prompt_context(f"prompts/sdd/{phase}.md")
    static_b = bytes_len(text)
    static_t = tokens(text)
    total_static += static_t
    # Conservative envelope: if a real change directory exists, treat all current artifacts as
    # available upstream payload for the phase. This intentionally tests the worst handoff case.
    art_t = artifact_tok
    used = static_t + art_t
    model = models[phase]
    cap = model_caps[phase]
    use = f"{pct(used, cap):.1f}%" if cap else "n/a"
    status = level(used, cap) if cap else "UNKNOWN"
    print(f"{phase:<14} {model:<23} {static_t:>7} t {art_t:>7} t {used:>7} t {cap or 0:>8} {use:>7} {status}")

print()
print("Context-flow interpretation")
print("----------------------------")
print(f"Static phase context total: {total_static} tokens")
if artifact_files():
    print(f"Current change artifact envelope: {artifact_tok} tokens ({artifact_total} bytes)")
    print("Artifact envelope is deliberately conservative: it assumes every existing change artifact is carried into every phase.")
else:
    print("No SDD_CHANGE artifact directory supplied; no dynamic artifact payload was added.")

print()
print("Model limits")
for name, cap in limits.items():
    print(f"- {name}: {cap} context tokens")

print()
print("Recommended run")
print("  SDD_CHANGE=<change-name> ./tools/run-context-flow-test.sh")
print("Optional model mapping")
print("  TONY_MODEL_SDD_APPLY=ollama/qwen3-coder:30b")
print("  TONY_PHASE_MODELS='sdd-explore=ollama/omnicoder:9b,sdd-apply=ollama/qwen3-coder:30b'")
print()
print("STATUS: this is a budget/envelope test, not a live model inference test.")
print("A live test must capture the actual OpenCode request payload/token usage during a real SDD run.")
PY

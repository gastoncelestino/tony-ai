#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: Python 3 is required."
  exit 2
fi

python3 - <<'PY'
import json, math, os, re, subprocess
from pathlib import Path

ROOT = Path.cwd()
PHASES = ["sdd-init","sdd-onboard","sdd-explore","sdd-propose","sdd-spec","sdd-design","sdd-tasks","sdd-apply","sdd-verify","sdd-archive"]
COMMON = "skills/_shared/sdd-phase-common.md"
ORCH = "prompts/agents/tony-orchestrator.md"
CONFIG = "opencode.json"


def git_show(path):
    p = subprocess.run(["git", "show", f"HEAD:{path}"], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return p.stdout if p.returncode == 0 else ""

def tok(s):
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(s))
    except Exception:
        return math.ceil(len(s.encode()) / 4)

def refs(path, seen=None):
    seen = set() if seen is None else seen
    if path in seen: return []
    seen.add(path)
    text = git_show(path)
    if not text: return []
    out = [path]
    for raw in re.findall(r"\{file:([^}]+)\}", text):
        nested = raw
        if nested.startswith("./"):
            nested = str((Path(path).parent / nested[2:]).as_posix())
        out += refs(nested, seen)
    return out

def phase_static(phase):
    return "\n".join(git_show(p) for p in refs(f"prompts/sdd/{phase}.md")) + "\n" + git_show(COMMON)

def model_name(config, phase):
    default = config["agent"]["tony-orchestrator"].get("model", "unknown")
    env = os.getenv(f"TONY_MODEL_{phase.upper().replace('-', '_')}")
    if env: return env
    for item in os.getenv("TONY_PHASE_MODELS", "").split(","):
        if "=" in item:
            p, m = item.split("=", 1)
            if p == phase: return m
    return default

def limits(config):
    models = config.get("provider", {}).get("ollama", {}).get("models", {})
    return {n: int(v.get("limit", {}).get("context", v.get("options", {}).get("numCtx", 0))) for n,v in models.items()}

def pct(n, cap): return n * 100 / cap if cap else 0

def status(n, cap):
    if not cap: return "UNKNOWN"
    p = pct(n, cap)
    return "CRITICAL" if p >= 90 else "HIGH" if p >= 75 else "WATCH" if p >= 50 else "SAFE"

def artifacts():
    change = os.getenv("SDD_CHANGE", "").strip()
    if not change: return []
    roots = [ROOT/"openspec"/"changes"/change, ROOT/"changes"/change]
    return sorted({p for r in roots if r.is_dir() for p in r.rglob("*") if p.is_file()})

def selected_artifacts(files):
    raw = os.getenv("SDD_ARTIFACTS", "").strip()
    if not raw: return files
    wanted = {x.strip() for x in raw.split(",") if x.strip()}
    return [p for p in files if str(p.relative_to(ROOT)) in wanted or p.name in wanted]

def byte_len(s): return len(s.encode("utf-8"))

with open(CONFIG, encoding="utf-8") as f: config = json.load(f)
model_limits = limits(config)
files = artifacts()
chosen = selected_artifacts(files)

print("\nTony AI — SDD Context Flow / Artifact Reuse Test")
print("================================================")
print("Goal: measure what crosses phase boundaries, not merely artifact size.")
print("Reference-first assumption: artifacts are stored by key/path and phases retrieve only selected material.")
print(f"Change: {os.getenv('SDD_CHANGE') or 'none'}")
print(f"Artifacts discovered: {len(files)}; selected for flow: {len(chosen)}")

print("\nARTIFACT INVENTORY")
print("------------------")
if chosen:
    for p in chosen:
        text = p.read_text(encoding="utf-8", errors="replace")
        print(f"{p.relative_to(ROOT)}  {byte_len(text)} B  {tok(text)} tok")
else:
    print("No artifacts selected. Run with SDD_CHANGE=<change-name>.")

print("\nPHASE FLOW")
print("----------")
print(f"{'PHASE':<14} {'MODEL':<23} {'STATIC':>8} {'RETRIEVED':>10} {'INPUT':>8} {'LIMIT':>8} {'USE':>7} STATUS")
print("-" * 100)

# A manifest may describe which upstream artifacts each phase needs.
manifest = {}
manifest_path = os.getenv("SDD_FLOW_MANIFEST", "")
if manifest_path and Path(manifest_path).exists():
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

previous_output = 0
for phase in PHASES:
    static = tok(phase_static(phase))
    model = model_name(config, phase)
    cap = model_limits.get(model.split("/",1)[-1], 0)
    spec = manifest.get(phase, {}) if isinstance(manifest, dict) else {}
    selected = spec.get("artifacts", []) if isinstance(spec, dict) else []
    if selected:
        phase_files = [p for p in chosen if str(p.relative_to(ROOT)) in selected or p.name in selected]
    else:
        phase_files = []
    retrieved = sum(tok(p.read_text(encoding="utf-8", errors="replace")) for p in phase_files)
    reference = sum(tok(str(p.relative_to(ROOT))) for p in phase_files)
    prior = int(spec.get("previous_output_tokens", 0)) if isinstance(spec, dict) else 0
    input_tokens = static + retrieved + prior
    use = f"{pct(input_tokens, cap):.1f}%" if cap else "n/a"
    print(f"{phase:<14} {model:<23} {static:>8} {retrieved:>10} {input_tokens:>8} {cap or 0:>8} {use:>7} {status(input_tokens, cap)}")
    if phase == "sdd-explore": previous_output = retrieved

print("\nREUSE / DUPLICATION ANALYSIS")
print("----------------------------")
if not chosen:
    print("No dynamic artifact flow to analyze.")
else:
    full = sum(tok(p.read_text(encoding="utf-8", errors="replace")) for p in chosen)
    print(f"Available artifact corpus: {full} tokens")
    print("A phase counts as reference-first when SDD_FLOW_MANIFEST lists selected artifacts explicitly.")
    print("If a phase receives the entire corpus, duplication risk is the unselected corpus: full - retrieved.")
    print()
    for phase in PHASES:
        spec = manifest.get(phase, {}) if isinstance(manifest, dict) else {}
        selected = spec.get("artifacts", []) if isinstance(spec, dict) else []
        retrieved = sum(tok(p.read_text(encoding="utf-8", errors="replace")) for p in chosen if str(p.relative_to(ROOT)) in selected or p.name in selected)
        duplicated = max(0, full - retrieved) if selected else 0
        if selected:
            print(f"{phase:<14} retrieved={retrieved:>6} tok  duplicated={duplicated:>6} tok  reference={sum(tok(str(p.relative_to(ROOT))) for p in chosen if str(p.relative_to(ROOT)) in selected or p.name in selected):>5} tok")

print("\nMODEL LIMITS")
for name, cap in model_limits.items(): print(f"- {name}: {cap} context tokens")

print("\nManifest format")
print("  SDD_FLOW_MANIFEST=tools/context-flow.example.json ./tools/run-context-flow-test.sh")
print("  The manifest names only the artifact references each phase is expected to retrieve.")
print("\nSTATUS: reference-first flow test. It measures the expected transfer envelope; live OpenCode request capture remains a separate integration test.")
PY

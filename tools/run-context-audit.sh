#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
RESET='\033[0m'

PHASES=(sdd-init sdd-onboard sdd-explore sdd-propose sdd-spec sdd-design sdd-tasks sdd-apply sdd-verify sdd-archive)
COMMON="skills/_shared/sdd-phase-common.md"
CONFIG="opencode.json"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  printf '%bERROR%b: not inside a git repository.\n' "$RED" "$RESET"
  exit 2
fi

for ref in main dev; do
  if ! git rev-parse --verify "origin/$ref^{commit}" >/dev/null 2>&1; then
    printf '%bERROR%b: origin/%s is not available. Run: git fetch origin --prune\n' "$RED" "$ref" "$ref"
    exit 2
  fi
done

TOKENIZER='estimate'
if command -v python3 >/dev/null 2>&1 && python3 - <<'PY' >/dev/null 2>&1
import tiktoken
tiktoken.get_encoding("cl100k_base")
PY
then
  TOKENIZER='cl100k_base'
fi

get_file() {
  local ref="$1" path="$2"
  git show "origin/$ref:$path" 2>/dev/null || true
}

count_tokens() {
  local text="$1"
  if [ "$TOKENIZER" = 'cl100k_base' ]; then
    printf '%s' "$text" | python3 -c 'import sys,tiktoken; e=tiktoken.get_encoding("cl100k_base"); print(len(e.encode(sys.stdin.read())))'
  else
    printf '%s' "$text" | wc -c | awk '{printf "%.0f", $1/4}'
  fi
}

resolve_refs() {
  local ref="$1" path="$2" seen="$3"
  local content refs nested
  case ",$seen," in *",$path,"*) return;; esac
  seen="$seen,$path"
  content="$(get_file "$ref" "$path")"
  [ -n "$content" ] || return
  printf '%s\n' "$path"
  refs=$(printf '%s\n' "$content" | grep -oE '\{file:[^}]+\}' | sed -E 's/^\{file:([^}]+)\}$/\1/' || true)
  while IFS= read -r nested; do
    [ -n "$nested" ] || continue
    case "$nested" in
      ./*) nested="$(dirname "$path")/${nested#./}";;
    esac
    resolve_refs "$ref" "$nested" "$seen"
  done <<< "$refs"
}

mcp_for_phase() {
  local phase="$1"
  local config
  config="$(get_file dev "$CONFIG")"
  printf '%s\n' "$config" | python3 -c '
import json,sys
phase=sys.argv[1]
data=json.load(sys.stdin)
agent=data.get("agent",{}).get(phase,{})
perm=agent.get("permission",{})
allowed=[k for k,v in perm.items() if v=="allow"]
print(",".join(allowed) if allowed else "none")
' "$phase"
}

printf '\n%bTony AI — Context Audit: main vs dev%b\n' "$GREEN" "$RESET"
printf 'Tokenizer: %s\n' "$TOKENIZER"
printf 'Common contract: %s\n\n' "$COMMON"

printf '%-14s %10s %10s %10s %10s %10s %10s\n' "PHASE" "MAIN B" "DEV B" "MAIN TOK" "DEV TOK" "SAVE" "MCP DEV"
printf '%-14s %10s %10s %10s %10s %10s %10s\n' "--------------" "----------" "----------" "----------" "----------" "----------" "----------"

total_main_bytes=0
total_dev_bytes=0
total_main_tokens=0
total_dev_tokens=0

for phase in "${PHASES[@]}"; do
  path="prompts/sdd/$phase.md"
  main_prompt="$(get_file main "$path")"
  dev_prompt="$(get_file dev "$path")"
  main_common="$(get_file main "$COMMON")"
  dev_common="$(get_file dev "$COMMON")"

  main_refs=$(resolve_refs main "$path" "" | sort -u)
  dev_refs=$(resolve_refs dev "$path" "" | sort -u)

  main_text="$main_prompt\n$main_common"
  dev_text="$dev_prompt\n$dev_common"

  while IFS= read -r refpath; do
    [ -n "$refpath" ] || continue
    [ "$refpath" = "$path" ] && continue
    main_text="$main_text\n$(get_file main "$refpath")"
  done <<< "$main_refs"
  while IFS= read -r refpath; do
    [ -n "$refpath" ] || continue
    [ "$refpath" = "$path" ] && continue
    dev_text="$dev_text\n$(get_file dev "$refpath")"
  done <<< "$dev_refs"

  main_bytes=$(printf '%s' "$main_text" | wc -c | tr -d ' ')
  dev_bytes=$(printf '%s' "$dev_text" | wc -c | tr -d ' ')
  main_tokens=$(count_tokens "$main_text")
  dev_tokens=$(count_tokens "$dev_text")

  if [ "$main_tokens" -gt 0 ]; then
    save=$(awk -v m="$main_tokens" -v d="$dev_tokens" 'BEGIN { printf "%.1f%%", (m-d)*100/m }')
  else save="n/a"; fi

  mcp=$(mcp_for_phase "$phase")
  printf '%-14s %10s %10s %10s %10s %10s %10s\n' "$phase" "$main_bytes" "$dev_bytes" "$main_tokens" "$dev_tokens" "$save" "$mcp"

  total_main_bytes=$((total_main_bytes + main_bytes))
  total_dev_bytes=$((total_dev_bytes + dev_bytes))
  total_main_tokens=$((total_main_tokens + main_tokens))
  total_dev_tokens=$((total_dev_tokens + dev_tokens))
done

printf '%-14s %10s %10s %10s %10s ' "TOTAL" "$total_main_bytes" "$total_dev_bytes" "$total_main_tokens" "$total_dev_tokens"
awk -v m="$total_main_tokens" -v d="$total_dev_tokens" 'BEGIN { printf "%.1f%%\n", (m-d)*100/m }'

echo
echo "References loaded are resolved transitively from each phase prompt."
echo "MCP column shows dev agent-level allow rules from opencode.json."
if [ "$TOKENIZER" = 'estimate' ]; then
  printf '%bNOTE%b: tiktoken/cl100k_base is not installed; token counts are byte/4 estimates.\n' "$YELLOW" "$RESET"
  echo "For exact counts: python3 -m pip install tiktoken"
fi

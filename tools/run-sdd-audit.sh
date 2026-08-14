#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GREEN='\033[32m'
RED='\033[31m'
RESET='\033[0m'

echo
echo "========================================"
echo "Tony AI - SDD Architecture Audit"
echo "========================================"
echo

if ! command -v bun >/dev/null 2>&1; then
  printf '%bERROR%b: Bun is not installed or not in PATH.\n' "$RED" "$RESET"
  echo "Install Bun on Ubuntu, then run this script again."
  echo
  echo "Expected command: bun --version"
  exit 2
fi

if command -v python3 >/dev/null 2>&1; then
  export TONY_PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  export TONY_PYTHON="python"
else
  printf '%bERROR%b: Python 3 is not installed or not in PATH.\n' "$RED" "$RESET"
  echo "Install Python 3, then run this script again."
  exit 2
fi

# Normalize the working tree before the audit. This fixes CRLF -> LF
# according to .gitattributes instead of hiding Git's warnings.
echo "▶ Normalizing repository line endings..."
git add --renormalize .

bun run tools/validate-sdd-flow.ts
EXIT_CODE=$?

echo
if [ "$EXIT_CODE" -eq 0 ]; then
  printf '%bAUDIT PASSED%b\n' "$GREEN" "$RESET"
else
  printf '%bAUDIT FAILED%b - review the output above\n' "$RED" "$RESET"
fi

exit "$EXIT_CODE"

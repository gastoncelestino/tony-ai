#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo
echo "========================================"
echo "Tony AI - SDD Architecture Audit"
echo "========================================"
echo

if ! command -v bun >/dev/null 2>&1; then
  echo "ERROR: Bun is not installed or not in PATH."
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
  echo "ERROR: Python 3 is not installed or not in PATH."
  echo "Install Python 3, then run this script again."
  exit 2
fi

bun run tools/validate-sdd-flow.ts
EXIT_CODE=$?

echo
if [ "$EXIT_CODE" -eq 0 ]; then
  echo "AUDIT PASSED"
else
  echo "AUDIT FAILED - review the output above"
fi

exit "$EXIT_CODE"

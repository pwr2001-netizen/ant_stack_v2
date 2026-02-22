#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[SMOKE] run discovery us"
bin/run_discovery.sh us >/dev/null 2>&1 || true
echo "[SMOKE] run discovery kr"
bin/run_discovery.sh kr >/dev/null 2>&1 || true
echo "[SMOKE] run tests (golden diff)"
bin/run_tests.sh
echo "[SMOKE] OK"

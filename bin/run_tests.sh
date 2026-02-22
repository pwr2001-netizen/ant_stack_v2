#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
mkdir -p var/tmp
normalize_discovery () {
  grep -E "^(ok: (true|false)|reason: |candidates_written: |passed: |failed: |added: |skipped: |\\[DONE\\] v2 discovery completed|\\{\"ok\": )" "$1" | sed -E "s/[[:space:]]+$//"
}
run_diff () {
  local golden="$1"; local current="$2"; local label="$3"
  if [ ! -f "$golden" ]; then echo "[ERROR] missing golden: $golden"; exit 2; fi
  if [ ! -f "$current" ]; then echo "[ERROR] missing current: $current"; exit 2; fi
  if diff -u "$golden" "$current" >/dev/null 2>&1; then echo "[PASS] $label"; else echo "[FAIL] $label (diff head)"; diff -u "$golden" "$current" | head -n 120; exit 1; fi
}
echo "[RUN] discovery us"
bin/run_discovery.sh us > var/tmp/_test_us_raw.txt 2>&1 || true
normalize_discovery var/tmp/_test_us_raw.txt > var/tmp/_test_us.norm.txt
run_diff tests/golden/out_us.norm.txt var/tmp/_test_us.norm.txt discovery_us
echo "[RUN] discovery kr"
bin/run_discovery.sh kr > var/tmp/_test_kr_raw.txt 2>&1 || true
normalize_discovery var/tmp/_test_kr_raw.txt > var/tmp/_test_kr.norm.txt
run_diff tests/golden/out_kr.norm.txt var/tmp/_test_kr.norm.txt discovery_kr

echo "[RESET] registrar sandbox reset (deterministic test)"
rm -f var/registrar/active/*.json 2>/dev/null || true
rm -f var/registrar/runlog/*.json 2>/dev/null || true
# ensure fixture exists (1 probation item)
mkdir -p var/discovery/probation
cat > var/discovery/probation/p_fixture_001.json <<'EOF'
{
  "v": 1,
  "url": "https://example.com/rss",
  "note": "fixture_for_registrar_to_active_1"
}
EOF


echo "[RUN] registrar compile/apply"
python3 ants/registrar/registrar_compile.py > var/tmp/_reg_compile_raw.txt 2>&1 || true
python3 ants/registrar/registrar_apply.py   > var/tmp/_reg_apply_raw.txt 2>&1 || true
python3 - <<'PY'
import json
from pathlib import Path

def norm(in_path, out_path):
    o = json.loads(Path(in_path).read_text(encoding="utf-8"))
    if isinstance(o, dict):
        o = dict(o)
        o.pop("ts", None)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

norm("var/registrar/runlog/compile_plan.json", "var/tmp/_compile_plan.norm.json")
norm("var/registrar/runlog/apply_result.json",  "var/tmp/_apply_result.norm.json")
PY
run_diff tests/golden/registrar/compile_plan.norm.json var/tmp/_compile_plan.norm.json registrar_compile_plan
run_diff tests/golden/registrar/apply_result.norm.json  var/tmp/_apply_result.norm.json  registrar_apply_result
python3 - <<'PY'
import json
from pathlib import Path

def norm(in_path, out_path):
    o = json.loads(Path(in_path).read_text(encoding="utf-8"))
    if isinstance(o, dict):
        o = dict(o)
        o.pop("ts", None)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

active = sorted(Path("var/registrar/active").glob("*.json"))
if not active:
    print("[SKIP] registrar_active_snapshot (no active)")
    raise SystemExit(0)
norm(str(active[0]), "var/tmp/_active_snapshot.norm.json")
PY
run_diff tests/golden/registrar/active_snapshot.norm.json var/tmp/_active_snapshot.norm.json registrar_active_snapshot

echo "[DONE] all tests pass"
echo "[DONE] discovery tests pass"

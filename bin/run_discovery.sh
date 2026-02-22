#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFG="$ROOT_DIR/config/paths.json"
LEGACY_ROOT="$HOME/ant_stack"

# 그룹명(기본 us). 필요하면: bin/run_discovery.sh kr
GROUP_NAME="${1:-us}"

echo "[INFO] v2 root: $ROOT_DIR"
echo "[INFO] legacy root: $LEGACY_ROOT"
echo "[INFO] config: $CFG"
echo "[INFO] group: $GROUP_NAME"

mkdir -p "$ROOT_DIR/var/discovery/seeds"
mkdir -p "$ROOT_DIR/var/discovery/candidates_queue"
mkdir -p "$ROOT_DIR/var/discovery/probation"
mkdir -p "$ROOT_DIR/var/discovery/runlog"
mkdir -p "$ROOT_DIR/var/tmp"

export CANDIDATES_DIR="$ROOT_DIR/var/discovery/candidates_queue"
export PROBATION_DIR="$ROOT_DIR/var/discovery/probation"
export RUNLOG_DIR="$ROOT_DIR/var/discovery/runlog"

# v2 fixtures seed 리스트(없으면 빈 파일) -> legacy seed json 생성에 사용
SEEDS_US_TXT="$ROOT_DIR/tests/fixtures/seeds_us.txt"
SEEDS_KR_TXT="$ROOT_DIR/tests/fixtures/seeds_kr.txt"

# (A) URL 목록 만들기(결정적)
TMP_URLS="$ROOT_DIR/var/tmp/_seed_urls.txt"
: > "$TMP_URLS"
if [ "$GROUP_NAME" = "kr" ]; then
  [ -f "$SEEDS_KR_TXT" ] && cat "$SEEDS_KR_TXT" >> "$TMP_URLS"
else
  [ -f "$SEEDS_US_TXT" ] && cat "$SEEDS_US_TXT" >> "$TMP_URLS"
fi
sed -i "s/[[:space:]]\\+$//" "$TMP_URLS"
sed -i "/^$/d" "$TMP_URLS"
sort -u "$TMP_URLS" -o "$TMP_URLS"

# (B) JSON array 생성(legacy가 요구하는 가장 흔한 형태)
TMP_JSON="$ROOT_DIR/var/tmp/${GROUP_NAME}.json"
printf "%s\\n" "[" > "$TMP_JSON"
first=1
while IFS= read -r url; do
  if [ $first -eq 1 ]; then first=0; else printf "%s\\n" "," >> "$TMP_JSON"; fi
  printf "  \\"%s\\"" "$url" >> "$TMP_JSON"
done < "$TMP_URLS"
printf "%s\\n" "" >> "$TMP_JSON"
printf "%s\\n" "]" >> "$TMP_JSON"

# (C) legacy가 어디를 보든 잡히게 다중 경로로 주입 (로직 수정 0)
cd "$LEGACY_ROOT"
mkdir -p seeds data seed_registry var/discovery/seeds bin 2>/dev/null || true

# 가장 가능성 높은 패턴들: seeds/<GROUP>.json, <GROUP>.json, data/<GROUP>.json, seed_registry/<GROUP>.json
cp -f "$TMP_JSON" "./${GROUP_NAME}.json"
cp -f "$TMP_JSON" "./seeds/${GROUP_NAME}.json"
cp -f "$TMP_JSON" "./data/${GROUP_NAME}.json"
cp -f "$TMP_JSON" "./seed_registry/${GROUP_NAME}.json"
cp -f "$TMP_JSON" "./var/discovery/seeds/${GROUP_NAME}.json"

# 레거시가 seeds.json을 직접 찾는 경우도 대비(그룹별 파일을 seeds.json으로도 복사)
cp -f "$TMP_JSON" "./seeds.json"
cp -f "$TMP_JSON" "./bin/seeds.json" 2>/dev/null || true

echo "[INFO] injected seed json candidates:"
ls -la "./${GROUP_NAME}.json" "./seeds/${GROUP_NAME}.json" "./data/${GROUP_NAME}.json" "./seed_registry/${GROUP_NAME}.json" "./seeds.json" 2>/dev/null || true

# (D) legacy 실행 스크립트 선택 + 그룹 인자 전달(핵심)
LEGACY_SCRIPT=""
for p in "bin/run_discovery_group.sh" "bin/run_discovery_batch.sh" "run_discovery_group.sh" "run_discovery_batch.sh" "bin/run_discovery.sh" "run_discovery.sh"; do
  if [ -f "$p" ]; then LEGACY_SCRIPT="$p"; break; fi
done
if [ -z "$LEGACY_SCRIPT" ]; then
  echo "[ERROR] legacy discovery script not found under $LEGACY_ROOT"
  exit 2
fi

echo "[INFO] using legacy script: $LEGACY_SCRIPT"
echo "[INFO] calling with GROUP_NAME arg: $GROUP_NAME"
bash "$LEGACY_SCRIPT" "$GROUP_NAME"

echo "[DONE] v2 discovery completed"

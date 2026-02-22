#!/usr/bin/env bash
set -euo pipefail

SEED_JSON="${1:-}"
if [ -z "${SEED_JSON}" ] || [ ! -f "${SEED_JSON}" ]; then
  echo "ok: false"
  echo "reason: seed_json_missing"
  exit 1
fi

# group name: seed file basename (without .json)
GROUP_NAME="$(basename "${SEED_JSON}" .json)"

QUEUE="registry/candidates/candidate_feeds_queue_${GROUP_NAME}.jsonl"
PROB="registry/probation/probation_feeds_${GROUP_NAME}.jsonl"
TOMB="registry/tombstone/tombstone_feeds_${GROUP_NAME}.jsonl"
RUNLOG="logs/discovery_runlog.jsonl"

mkdir -p "$(dirname "$QUEUE")" "$(dirname "$PROB")" "$(dirname "$TOMB")" "$(dirname "$RUNLOG")"

# 1) seed -> candidates queue
python3 ./bin/seed_to_candidates_v1.py "${SEED_JSON}" "${QUEUE}" | sed -n '1,1p'
candidates_written="$(wc -l < "${QUEUE}" 2>/dev/null || echo 0)"
echo "ok: true"
echo "candidates_written: ${candidates_written}"

# 2) evaluate -> split (needs bin/feed_eval_v1.py already created by you; if missing, fail fast)
if [ ! -x ./bin/feed_eval_v1.py ]; then
  echo "ok: false"
  echo "reason: missing_feed_eval_v1_py"
  exit 2
fi

# evaluator: stdin queue -> stdout results
# split: results -> probation/tombstone files
eval_json="$(cat "${QUEUE}" | ./bin/feed_eval_v1.py | ./bin/split_eval_v1.py "${PROB}" "${TOMB}")"
echo "${eval_json}"

passed="$(wc -l < "${PROB}" 2>/dev/null || echo 0)"
failed="$(wc -l < "${TOMB}" 2>/dev/null || echo 0)"

echo "ok: true"
echo "passed: ${passed}"
echo "failed: ${failed}"

# (추후 registrar 편입/중복필터/added/skipped는 다음 단계에서)
added=0
skipped=0

python3 ./bin/append_runlog_v1.py "${RUNLOG}" "${GROUP_NAME}" "${SEED_JSON}" "${candidates_written}" "${passed}" "${failed}" "${added}" "${skipped}" >/dev/null || true

echo "ok: true"
echo "added: ${added}"
echo "skipped: ${skipped}"

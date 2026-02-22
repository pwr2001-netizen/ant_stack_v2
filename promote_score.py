#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
promote_score.py (v2)
- 입력: var/registrar/probation_queue/*.json
- 참고: var/registrar/probation_history/<sha1>.json (없으면 점수=기본)
- 출력: var/registrar/promote_plan/*.json
- 결정성: 파일명 정렬, history는 "마지막 이벤트 1개"만 사용
- 네트워크 금지, 무상태
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
from datetime import datetime, timezone

V = 2

DEFAULT_PROBATION_QUEUE = "var/registrar/probation_queue"
DEFAULT_PROMOTE_PLAN = "var/registrar/promote_plan"
DEFAULT_RUNLOG = "var/registrar/promote_runlog"
DEFAULT_HISTORY_DIR = "var/registrar/probation_history"

def now_iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def json_dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

def safe_write_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json_dump(obj))
        f.write("\n")
    os.replace(tmp, path)

def sha1_hex(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def clamp01(x):
    try:
        x = float(x)
    except Exception:
        return None
    if x < 0: x = 0.0
    if x > 1: x = 1.0
    return x

def items_bonus(n) -> int:
    """items_count 보너스(결정적, 작은 값)"""
    try:
        n = int(n)
    except Exception:
        return 0
    if n <= 0:
        return 0
    # log 기반 보너스: 1~3
    b = int(min(3, max(1, round(math.log10(n + 1)))))
    return b

def load_latest_metrics(history_dir: str, key: str) -> dict:
    """
    history/<key>.json에서 최신 metrics 1개 추출
    key는 sha1(권장) 또는 canonical 기반
    실패 시 {} 반환
    """
    path = os.path.join(history_dir, f"{key}.json")
    if not os.path.exists(path):
        return {}
    try:
        h = load_json(path)
        evs = h.get("events") if isinstance(h, dict) else None
        if not isinstance(evs, list) or not evs:
            return {}
        last = evs[-1] if isinstance(evs[-1], dict) else {}
        m = (last.get("metrics") or {}) if isinstance(last, dict) else {}
        return {
            "valid_ratio": clamp01(m.get("valid_ratio")),
            "error_rate": clamp01(m.get("error_rate")),
            "dup_ratio": clamp01(m.get("dup_ratio")),
            "items_count": m.get("items_count"),
            "history_file": path,
            "history_ts": last.get("ts"),
        }
    except Exception:
        return {}

def score_probation_item(item: dict, history_dir: str) -> dict:
    """
    score = retest_bonus(10 if probation_retest_enqueue)
          + round(valid_ratio*20)
          - round(error_rate*30)
          - round(dup_ratio*15)
          + bonus(items_count)
    history 없으면 base만.
    """
    canonical = (item.get("canonical_url") or "").strip()
    act = item.get("action")

    score = 0
    reasons = []
    debug = {"history_used": False, "history_file": None}

    if not canonical:
        return {"score": 0, "reasons": ["missing_canonical(score=0)"], "metrics": {}, "debug": debug}

    if act == "probation_retest_enqueue":
        score += 10
        reasons.append("retest_bonus(+10)")

    # history key: sha1 우선, 없으면 canonical sha1
    sha1 = (item.get("sha1") or "").strip() or sha1_hex(canonical)
    metrics = load_latest_metrics(history_dir, sha1)
    if metrics:
        debug["history_used"] = True
        debug["history_file"] = metrics.get("history_file")

        vr = metrics.get("valid_ratio")
        er = metrics.get("error_rate")
        dr = metrics.get("dup_ratio")
        ic = metrics.get("items_count")

        if vr is not None:
            add = int(round(vr * 20))
            score += add
            reasons.append(f"valid_ratio({vr})*20=+{add}")
        if er is not None:
            sub = int(round(er * 30))
            score -= sub
            reasons.append(f"error_rate({er})*30=-{sub}")
        if dr is not None:
            sub = int(round(dr * 15))
            score -= sub
            reasons.append(f"dup_ratio({dr})*15=-{sub}")

        b = items_bonus(ic)
        if b:
            score += b
            reasons.append(f"items_bonus({ic})=+{b}")

    else:
        reasons.append("no_history_metrics(+0)")

    # 결정적: 최저 0 보장
    if score < 0:
        score = 0
        reasons.append("floor_to_zero")

    return {"score": int(score), "reasons": reasons, "metrics": metrics or {}, "debug": debug}

def decide_action(score: int, promote_threshold: int, keep_threshold: int) -> str:
    if score >= promote_threshold:
        return "promote_to_active"
    if score >= keep_threshold:
        return "keep_in_probation"
    return "keep_tombstone"

def main() -> int:
    ap = argparse.ArgumentParser(description="Score probation items and write promote plans (with history).")
    ap.add_argument("--probation-queue", default=DEFAULT_PROBATION_QUEUE)
    ap.add_argument("--promote-plan", default=DEFAULT_PROMOTE_PLAN)
    ap.add_argument("--runlog", default=DEFAULT_RUNLOG)
    ap.add_argument("--history-dir", default=DEFAULT_HISTORY_DIR)
    ap.add_argument("--max", type=int, default=200)
    ap.add_argument("--promote-threshold", type=int, default=20)
    ap.add_argument("--keep-threshold", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out = {
        "v": V,
        "action": "promote_score",
        "ok": True,
        "ts": now_iso_utc(),
        "paths": {
            "probation_queue": args.probation_queue,
            "promote_plan": args.promote_plan,
            "runlog": args.runlog,
            "history_dir": args.history_dir,
        },
        "thresholds": {
            "promote_threshold": args.promote_threshold,
            "keep_threshold": args.keep_threshold,
        },
        "counts": {"found": 0, "planned": 0, "invalid": 0},
        "items": [],
    }

    files = sorted(glob.glob(os.path.join(args.probation_queue, "*.json")))
    out["counts"]["found"] = len(files)
    files = files[: max(0, args.max)]

    os.makedirs(args.promote_plan, exist_ok=True)
    os.makedirs(args.runlog, exist_ok=True)

    for path in files:
        it = {"file": path, "ok": False, "canonical_url": "", "score": 0, "decision": "", "plan_file": None, "error": None}
        try:
            obj = load_json(path)
            canonical = (obj.get("canonical_url") or "").strip()
            it["canonical_url"] = canonical

            if not canonical:
                out["counts"]["invalid"] += 1
                it["error"] = {"code": "missing_canonical", "message": "canonical_url required"}
                it["decision"] = "invalid"
                it["ok"] = True
                out["items"].append(it)
                continue

            score_info = score_probation_item(obj, args.history_dir)
            score = int(score_info["score"])
            decision = decide_action(score, args.promote_threshold, args.keep_threshold)

            it["score"] = score
            it["decision"] = decision
            it["ok"] = True

            sha1 = (obj.get("sha1") or "").strip() or sha1_hex(canonical)
            # plan payload
            plan = {
                "v": 1,
                "action": "promote_plan_item",
                "ts": now_iso_utc(),
                "ok": True,
                "canonical_url": canonical,
                "sha1": sha1,
                "score": score,
                "decision": decision,
                "reasons": score_info.get("reasons", []),
                "history": {
                    "used": bool(score_info.get("debug", {}).get("history_used")),
                    "file": score_info.get("debug", {}).get("history_file"),
                    "metrics": score_info.get("metrics", {}),
                },
                "source": {
                    "from_probation_file": path,
                    "probation_action": obj.get("action"),
                    "request_ts": (obj.get("source") or {}).get("request_ts"),
                    "operator": (obj.get("source") or {}).get("operator"),
                    "reason": (obj.get("source") or {}).get("reason"),
                },
            }

            ts_tag = ((plan["source"]["request_ts"] or plan["ts"]) or now_iso_utc())
            ts_tag = ts_tag.replace("-", "").replace(":", "").replace("+00:00", "Z")
            fname = f"{sha1}_{ts_tag}.json"
            plan_path = os.path.join(args.promote_plan, fname)
            it["plan_file"] = plan_path

            out["counts"]["planned"] += 1
            if not args.dry_run:
                safe_write_json(plan_path, plan)

            out["items"].append(it)

        except Exception as e:
            it["error"] = {"code": "exception", "message": str(e)}
            it["ok"] = False
            out["ok"] = False
            out["items"].append(it)

    ts_tag = out["ts"].replace("-", "").replace(":", "").replace("+00:00", "Z")
    if not args.dry_run:
        safe_write_json(os.path.join(args.runlog, f"promote_score_{ts_tag}.json"), out)

    print(json_dump(out))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
promote_apply.py
- 입력: var/registrar/promote_plan/*.json
- 처리:
   - promote_to_active      => active_snapshot에 추가(또는 갱신)
   - keep_in_probation      => active 변화 없음 (runlog에만 기록)
   - keep_tombstone         => active 변화 없음 (runlog에만 기록)
- plan 파일은 처리 후 runlog/{done,skipped,bad} 로 이동
- 결정성: 파일명 정렬 + 동일 규칙
- active 없으면 SKIP 허용(결정적) : active_snapshot은 "비어도 OK"
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from datetime import datetime, timezone

V = 1

DEFAULT_PROMOTE_PLAN = "var/registrar/promote_plan"
DEFAULT_RUNLOG = "var/registrar/promote_runlog"
DEFAULT_ACTIVE_SNAPSHOT = "var/registrar/active_snapshot/active.json"

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

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def move_file(src: str, dst_dir: str) -> str:
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(src))
    if os.path.exists(dst):
        base, ext = os.path.splitext(dst)
        i = 1
        while os.path.exists(f"{base}.{i}{ext}"):
            i += 1
        dst = f"{base}.{i}{ext}"
    os.replace(src, dst)
    return dst

def load_active(path: str) -> dict:
    if not os.path.exists(path):
        return {"v": 1, "action": "active_snapshot", "ok": True, "ts": now_iso_utc(), "items": []}
    try:
        obj = load_json(path)
        if isinstance(obj, dict) and isinstance(obj.get("items"), list):
            return obj
    except Exception:
        pass
    # 실패해도 throw 금지: 빈 snapshot으로 재시작(봉인)
    return {"v": 1, "action": "active_snapshot", "ok": True, "ts": now_iso_utc(), "items": []}

def upsert_active(active: dict, canonical_url: str, sha1: str, score: int, meta: dict) -> tuple[dict, bool]:
    """
    active.items 내 동일 canonical_url 있으면 갱신, 없으면 추가
    반환: (active, changed)
    """
    items = active.get("items") or []
    changed = False
    for it in items:
        if isinstance(it, dict) and it.get("canonical_url") == canonical_url:
            # 갱신
            it["sha1"] = sha1
            it["score"] = score
            it["updated_ts"] = now_iso_utc()
            it["meta"] = meta
            changed = True
            break
    else:
        items.append({
            "canonical_url": canonical_url,
            "sha1": sha1,
            "score": score,
            "added_ts": now_iso_utc(),
            "meta": meta,
        })
        changed = True

    active["items"] = items
    active["ts"] = now_iso_utc()
    return active, changed

def main() -> int:
    ap = argparse.ArgumentParser(description="Apply promote_plan into active_snapshot (deterministic).")
    ap.add_argument("--promote-plan", default=DEFAULT_PROMOTE_PLAN)
    ap.add_argument("--runlog", default=DEFAULT_RUNLOG)
    ap.add_argument("--active-snapshot", default=DEFAULT_ACTIVE_SNAPSHOT)
    ap.add_argument("--max", type=int, default=200)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out = {
        "v": V,
        "action": "promote_apply",
        "ok": True,
        "ts": now_iso_utc(),
        "paths": {
            "promote_plan": args.promote_plan,
            "runlog": args.runlog,
            "active_snapshot": args.active_snapshot,
        },
        "counts": {"found": 0, "processed": 0, "promoted": 0, "skipped": 0, "invalid": 0},
        "items": [],
        "note": "active_snapshot may remain empty; this is deterministic and allowed.",
    }

    files = sorted(glob.glob(os.path.join(args.promote_plan, "*.json")))
    out["counts"]["found"] = len(files)
    files = files[: max(0, args.max)]

    done_dir = os.path.join(args.runlog, "done")
    skip_dir = os.path.join(args.runlog, "skipped")
    bad_dir = os.path.join(args.runlog, "bad")
    os.makedirs(args.runlog, exist_ok=True)

    active = load_active(args.active_snapshot)
    active_changed = False

    for path in files:
        it = {"file": path, "ok": False, "decision": "", "canonical_url": "", "moved_to": None, "error": None}
        try:
            plan = load_json(path)
            if not isinstance(plan, dict) or plan.get("action") != "promote_plan_item" or not plan.get("ok", False):
                out["counts"]["invalid"] += 1
                it["decision"] = "invalid"
                it["error"] = {"code": "bad_plan", "message": "invalid promote_plan_item"}
                if not args.dry_run:
                    it["moved_to"] = move_file(path, bad_dir)
                it["ok"] = True
                out["items"].append(it)
                continue

            canonical = (plan.get("canonical_url") or "").strip()
            sha1 = (plan.get("sha1") or "").strip()
            decision = plan.get("decision")
            score = int(plan.get("score") or 0)

            it["canonical_url"] = canonical
            it["decision"] = decision

            if decision == "promote_to_active":
                meta = {
                    "source": plan.get("source") or {},
                    "promoted_ts": now_iso_utc(),
                }
                active, changed = upsert_active(active, canonical, sha1, score, meta)
                active_changed = active_changed or changed
                out["counts"]["promoted"] += 1
                if not args.dry_run:
                    it["moved_to"] = move_file(path, done_dir)
                it["ok"] = True
                out["items"].append(it)

            else:
                # keep_in_probation / keep_tombstone : active 변화 없음
                out["counts"]["skipped"] += 1
                if not args.dry_run:
                    it["moved_to"] = move_file(path, skip_dir)
                it["ok"] = True
                out["items"].append(it)

            out["counts"]["processed"] += 1

        except Exception as e:
            out["ok"] = False
            it["decision"] = "error"
            it["error"] = {"code": "exception", "message": str(e)}
            it["ok"] = False
            out["items"].append(it)

    # active snapshot 저장
    if not args.dry_run and active_changed:
        os.makedirs(os.path.dirname(args.active_snapshot), exist_ok=True)
        safe_write_json(args.active_snapshot, active)

    # runlog 저장
    ts_tag = out["ts"].replace("-", "").replace(":", "").replace("Z", "Z").replace("+00:00", "Z")
    if not args.dry_run:
        safe_write_json(os.path.join(args.runlog, f"promote_apply_{ts_tag}.json"), out)

    print(json_dump(out))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

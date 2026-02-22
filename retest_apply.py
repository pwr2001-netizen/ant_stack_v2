#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
retest_apply.py
- var/registrar/retest_queue/*.json 을 결정적으로 처리
- "허용된 경우에만" var/registrar/probation_queue 로 재투입(enqueue)
- 처리 결과는 var/registrar/retest_runlog 로 기록
- 원칙: tombstone 자동 해제 금지
  => 기본 정책: tombstone 목록에 존재하는 canonical_url만 probation으로 재진입 가능
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

V = 1

DEFAULT_RETEST_QUEUE = "var/registrar/retest_queue"
DEFAULT_RETEST_RUNLOG = "var/registrar/retest_runlog"
DEFAULT_PROBATION_QUEUE = "var/registrar/probation_queue"

# 안전 기본값: tombstone 파일을 명시하지 않으면 "허용 0"으로 동작 (봉인 유지)
DEFAULT_TOMBSTONE_FILE = "var/registrar/tombstone.jsonl"

URL_RE = re.compile(r"^https?://", re.IGNORECASE)

def now_iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def json_dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

def sha1_hex(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def safe_write_text(path: str, text: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")
    os.replace(tmp, path)

def safe_write_json(path: str, obj) -> None:
    safe_write_text(path, json_dump(obj))

def read_json_file(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def move_file(src: str, dst_dir: str) -> str:
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(src))
    # 충돌 시 결정적으로 suffix 추가
    if os.path.exists(dst):
        base, ext = os.path.splitext(dst)
        i = 1
        while os.path.exists(f"{base}.{i}{ext}"):
            i += 1
        dst = f"{base}.{i}{ext}"
    os.replace(src, dst)
    return dst

def load_tombstone_set(path: str) -> set[str]:
    """
    tombstone 목록을 안전하게 읽는다(결정적).
    우선순위:
      1) JSONL: 각 줄이 JSON dict이면 canonical_url/url/target_url에서 추출
      2) TXT: 각 줄이 URL이면 그대로 추가
      3) JSON: 파일 전체가 유효한 JSON(list/dict)일 때만 처리
    파일이 없거나 파싱 실패면 빈 set (=> allow none, sealed)
    """
    s: set[str] = set()
    if not path or not os.path.exists(path):
        return s

    def add_url(u: str):
        u = (u or "").strip()
        if URL_RE.match(u):
            s.add(u)

    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

        # 1) JSONL/TXT 라인 처리 우선
        any_line = False
        for line in lines:
            line = line.strip()
            if not line:
                continue
            any_line = True

            if line.startswith("{") and line.endswith("}"):
                try:
                    d = json.loads(line)
                    if isinstance(d, dict):
                        add_url(d.get("canonical_url") or d.get("url") or d.get("target_url") or "")
                        continue
                except Exception:
                    continue

            # TXT URL 라인
            add_url(line)

        # 라인 방식으로 하나라도 얻었으면 종료
        if s or not any_line:
            return s

        # 2) 라인 방식으로 못 얻었으면 JSON 전체 파싱 시도
        raw = "\n".join(lines).strip()
        if not raw:
            return s

        if raw[0] in "[{":
            obj = json.loads(raw)
            if isinstance(obj, dict):
                items = obj.get("items", [])
                if isinstance(items, list):
                    for it in items:
                        if isinstance(it, str):
                            add_url(it)
                        elif isinstance(it, dict):
                            add_url(it.get("canonical_url") or it.get("url") or it.get("target_url") or "")
                else:
                    add_url(obj.get("canonical_url") or obj.get("url") or obj.get("target_url") or "")
            elif isinstance(obj, list):
                for it in obj:
                    if isinstance(it, str):
                        add_url(it)
                    elif isinstance(it, dict):
                        add_url(it.get("canonical_url") or it.get("url") or it.get("target_url") or "")
        return s

    except Exception:
        return set()
def make_probation_payload(req: dict) -> dict:
    """
    probation 재진입 envelope (결정적 최소 필드)
    """
    canonical = req.get("canonical_url", "")
    h = req.get("sha1", "") or sha1_hex(canonical)
    return {
        "v": 1,
        "action": "probation_retest_enqueue",
        "ts": now_iso_utc(),
        "ok": True,
        "canonical_url": canonical,
        "sha1": h,
        "source": {
            "from": "retest_queue",
            "request_ts": req.get("ts"),
            "operator": req.get("operator"),
            "reason": req.get("reason"),
            "queue_file": req.get("queue_file"),
        },
    }

def validate_request(req: dict) -> tuple[bool, dict | None]:
    if not isinstance(req, dict):
        return False, {"code": "bad_json", "message": "Request must be a JSON object"}
    if req.get("v") != 1:
        return False, {"code": "bad_v", "message": "Unsupported v"}
    if req.get("action") != "retest_request":
        return False, {"code": "bad_action", "message": "action must be retest_request"}
    if not req.get("ok", False):
        return False, {"code": "not_ok", "message": "request ok must be true"}
    canonical = (req.get("canonical_url") or "").strip()
    if not canonical or not URL_RE.match(canonical):
        return False, {"code": "bad_canonical", "message": "canonical_url invalid"}
    sha1 = (req.get("sha1") or "").strip()
    if sha1 and sha1 != sha1_hex(canonical):
        return False, {"code": "sha1_mismatch", "message": "sha1 does not match canonical_url"}
    return True, None

def main() -> int:
    ap = argparse.ArgumentParser(description="Apply retest_queue requests into probation_queue (allowed only).")
    ap.add_argument("--retest-queue", default=DEFAULT_RETEST_QUEUE)
    ap.add_argument("--retest-runlog", default=DEFAULT_RETEST_RUNLOG)
    ap.add_argument("--probation-queue", default=DEFAULT_PROBATION_QUEUE)
    ap.add_argument("--tombstone-file", default=DEFAULT_TOMBSTONE_FILE,
                    help="Tombstone list file. If missing/unreadable => allow none (sealed).")
    ap.add_argument("--max", type=int, default=200, help="Max requests per run (deterministic cap).")
    ap.add_argument("--dry-run", action="store_true", help="Do not move files or enqueue; just report.")
    args = ap.parse_args()

    out = {
        "v": V,
        "action": "retest_apply",
        "ok": True,
        "ts": now_iso_utc(),
        "paths": {
            "retest_queue": args.retest_queue,
            "retest_runlog": args.retest_runlog,
            "probation_queue": args.probation_queue,
            "tombstone_file": args.tombstone_file,
        },
        "counts": {
            "found": 0,
            "processed": 0,
            "enqueued": 0,
            "skipped": 0,
            "invalid": 0,
        },
        "items": [],  # per-file result (small)
        "note": "ALLOW only if canonical_url is currently tombstoned. No auto-untombstone.",
        "debug": {"tombstone_count": 0, "tombstone_sample": []},
    }

    # 결정적 처리 순서: 파일명 정렬
    files = sorted(glob.glob(os.path.join(args.retest_queue, "*.json")))
    out["counts"]["found"] = len(files)

    tombs = load_tombstone_set(args.tombstone_file)
    out["debug"]["tombstone_count"] = len(tombs)
    # sample first 5 deterministically
    out["debug"]["tombstone_sample"] = sorted(list(tombs))[:5]

    # 처리량 제한(결정적)
    files = files[: max(0, args.max)]

    os.makedirs(args.retest_runlog, exist_ok=True)
    os.makedirs(args.probation_queue, exist_ok=True)

    done_dir = os.path.join(args.retest_runlog, "done")
    bad_dir = os.path.join(args.retest_runlog, "bad")
    skip_dir = os.path.join(args.retest_runlog, "skipped")
    plan_dir = os.path.join(args.retest_runlog, "probation_enqueued")

    for path in files:
        item = {
            "file": path,
            "ok": False,
            "decision": "",
            "canonical_url": "",
            "moved_to": None,
            "enqueued_file": None,
            "error": None,
        }

        try:
            req = read_json_file(path)
            valid, err = validate_request(req)
            if not valid:
                out["counts"]["invalid"] += 1
                item["decision"] = "invalid"
                item["error"] = err
                if not args.dry_run:
                    item["moved_to"] = move_file(path, bad_dir)
                item["ok"] = True
                out["items"].append(item)
                continue

            canonical = req["canonical_url"].strip()
            item["canonical_url"] = canonical

            # 핵심 게이트: tombstone에 있어야만 probation 재투입 가능
            if canonical not in tombs:
                out["counts"]["skipped"] += 1
                item["decision"] = "skip_not_tombstoned"
                if not args.dry_run:
                    item["moved_to"] = move_file(path, skip_dir)
                item["ok"] = True
                out["items"].append(item)
                continue

            # enqueue probation payload
            payload = make_probation_payload(req)

            # 결정적 파일명: sha1_requestts (request ts 사용) + ".json"
            # request ts가 없으면 현재 ts를 쓰지만, 보통 req.ts 존재
            req_ts = (req.get("ts") or payload["ts"]).replace("-", "").replace(":", "").replace("Z", "Z")
            req_ts = req_ts.replace("+00:00", "Z")
            h = payload["sha1"]
            fname = f"{h}_{req_ts}.json"
            p_out = os.path.join(args.probation_queue, fname)

            if args.dry_run:
                item["decision"] = "enqueue_dry_run"
                item["enqueued_file"] = p_out
                item["ok"] = True
                out["counts"]["processed"] += 1
                out["counts"]["enqueued"] += 1
                out["items"].append(item)
                continue

            # 충돌 시 suffix (결정적 증가)
            if os.path.exists(p_out):
                base, ext = os.path.splitext(p_out)
                i = 1
                while os.path.exists(f"{base}.{i}{ext}"):
                    i += 1
                p_out = f"{base}.{i}{ext}"

            safe_write_json(p_out, payload)

            # runlog에도 동일 payload 복제(감사)
            os.makedirs(plan_dir, exist_ok=True)
            safe_write_json(os.path.join(plan_dir, os.path.basename(p_out)), payload)

            # request는 done으로 이동
            item["decision"] = "enqueued_to_probation"
            item["enqueued_file"] = p_out
            item["moved_to"] = move_file(path, done_dir)

            out["counts"]["processed"] += 1
            out["counts"]["enqueued"] += 1
            item["ok"] = True
            out["items"].append(item)

        except Exception as e:
            # throw 금지: ok=false로 기록하고 계속
            out["counts"]["processed"] += 1
            item["decision"] = "error"
            item["error"] = {"code": "exception", "message": str(e)}
            item["ok"] = False
            out["items"].append(item)
            out["ok"] = False

    # runlog 저장(결정적 파일명: ts)
    ts_tag = out["ts"].replace("-", "").replace(":", "").replace("Z", "Z").replace("+00:00", "Z")
    log_path = os.path.join(args.retest_runlog, f"retest_apply_{ts_tag}.json")
    if not args.dry_run:
        safe_write_json(log_path, out)

    print(json_dump(out))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

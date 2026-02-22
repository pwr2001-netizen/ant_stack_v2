#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
retest_request.py
- 입력 URL → canonicalize → sha1 계산 → var/registrar/retest_queue 에 request JSON 생성
- 결정적(R1), 네트워크 금지(R2), 무상태(R3), 실패는 throw 대신 ok=false (R6)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

V = 1

DEFAULT_QUEUE_DIR = "var/registrar/retest_queue"

URL_RE = re.compile(r"^https?://", re.IGNORECASE)

def now_iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def json_dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

def canonicalize_url(url: str) -> str:
    """
    최소 결정적 정규화:
    - strip
    - fragment 제거
    - scheme/host 소문자
    - default port 제거(80/443)
    - path 비어있으면 '/'
    - query는 유지(의도적)
    """
    u = url.strip()
    parts = urlsplit(u)

    scheme = (parts.scheme or "").lower()
    netloc = parts.netloc
    path = parts.path or "/"
    query = parts.query or ""
    fragment = ""  # drop

    # host:port lower
    if netloc:
        # split userinfo? keep as-is but lowercase host segment only
        # simplest deterministic: lowercase entire netloc
        netloc_l = netloc.lower()

        # drop default ports
        # NOTE: only safe when netloc is host:port (no IPv6 bracket parsing here)
        if scheme == "http" and netloc_l.endswith(":80"):
            netloc_l = netloc_l[:-3]
        if scheme == "https" and netloc_l.endswith(":443"):
            netloc_l = netloc_l[:-4]

        netloc = netloc_l

    return urlunsplit((scheme, netloc, path, query, fragment))

def sha1_hex(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def safe_write_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    data = json_dump(obj)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
        f.write("\n")
    os.replace(tmp, path)

def main() -> int:
    ap = argparse.ArgumentParser(description="Create a retest request JSON into retest_queue.")
    ap.add_argument("url", nargs="?", help="Target URL to retest (http/https).")
    ap.add_argument("--queue-dir", default=DEFAULT_QUEUE_DIR, help="Queue directory (default: var/registrar/retest_queue)")
    ap.add_argument("--reason", default="operator_retest_request", help="Reason string for audit trail.")
    ap.add_argument("--operator", default=os.environ.get("USER", "operator"), help="Operator name (audit).")
    ap.add_argument("--stdin", action="store_true", help="Read URL from stdin (first non-empty line).")
    ap.add_argument("--dry-run", action="store_true", help="Print request JSON to stdout only (do not write file).")
    args = ap.parse_args()

    url_in = args.url or ""
    if args.stdin:
        try:
            for line in sys.stdin.read().splitlines():
                line = line.strip()
                if line:
                    url_in = line
                    break
        except Exception:
            url_in = ""

    out = {
        "v": V,
        "action": "retest_request",
        "ok": False,
        "ts": now_iso_utc(),
        "input_url": url_in,
        "canonical_url": "",
        "sha1": "",
        "reason": args.reason,
        "operator": args.operator,
        "queue_file": "",
        "error": None,
    }

    # validate
    if not url_in or not URL_RE.match(url_in.strip()):
        out["error"] = {"code": "bad_url", "message": "URL must start with http:// or https://"}
        print(json_dump(out))
        return 0

    canonical = canonicalize_url(url_in)
    # sanity: must still look like http(s)://
    if not canonical or not URL_RE.match(canonical):
        out["error"] = {"code": "bad_canonical", "message": "Canonical URL invalid after normalization"}
        print(json_dump(out))
        return 0

    h = sha1_hex(canonical)
    out["canonical_url"] = canonical
    out["sha1"] = h

    # filename: sha1 + timestamp (YYYYMMDDTHHMMSSZ)
    ts_tag = out["ts"].replace("-", "").replace(":", "").replace("Z", "Z").replace("+00:00", "Z")
    ts_tag = ts_tag.replace("T", "T")  # keep T
    fname = f"{h}_{ts_tag}.json"
    qdir = args.queue_dir

    if args.dry_run:
        out["ok"] = True
        out["queue_file"] = os.path.join(qdir, fname)
        print(json_dump(out))
        return 0

    try:
        os.makedirs(qdir, exist_ok=True)
        path = os.path.join(qdir, fname)

        # idempotency guard: if same exact file exists, do not overwrite
        if os.path.exists(path):
            out["ok"] = True
            out["queue_file"] = path
            out["error"] = {"code": "already_exists", "message": "Request file already exists (same sha1 & ts)."}
            print(json_dump(out))
            return 0

        safe_write_json(path, out | {"ok": True, "queue_file": path})
        out["ok"] = True
        out["queue_file"] = path
        print(json_dump(out))
        return 0

    except Exception as e:
        out["error"] = {"code": "io_error", "message": str(e)}
        print(json_dump(out))
        return 0

if __name__ == "__main__":
    raise SystemExit(main())

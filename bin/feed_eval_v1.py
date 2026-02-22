#!/usr/bin/env python3
import sys, json, subprocess, shlex, re

MAX_BYTES = 200 * 1024
TIMEOUT  = 12

def curl_fetch(url: str):
    # -L follow, -s silent, -S show errors, --max-time total
    cmd = [
        "curl", "-L", "-sS",
        "--max-time", str(TIMEOUT),
        "--max-filesize", str(MAX_BYTES),
        "-D", "-",  # dump headers to stdout first
        url
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, p.stdout, p.stderr

def split_headers_body(raw: str):
    # curl -D - prints headers then body
    # headers end at first blank line
    m = re.split(r"\r?\n\r?\n", raw, maxsplit=1)
    if len(m) == 2:
        return m[0], m[1]
    return raw, ""

def parse_status(headers: str):
    # take last HTTP status line if redirects produced multiple
    lines = headers.splitlines()
    status_lines = [ln for ln in lines if ln.startswith("HTTP/")]
    if not status_lines:
        return 0
    last = status_lines[-1].split()
    if len(last) >= 2 and last[1].isdigit():
        return int(last[1])
    return 0

def header_value(headers: str, key: str):
    key_l = key.lower()
    for ln in headers.splitlines():
        if ":" in ln:
            k,v = ln.split(":",1)
            if k.strip().lower() == key_l:
                return v.strip()
    return ""

def looks_like_feed(body: str):
    b = body[:5000].lower()
    # RSS / Atom minimal signatures
    if "<rss" in b or "<rdf:rdf" in b or "<feed" in b:
        return True
    return False

def is_xmlish(ct: str):
    ct = (ct or "").lower()
    return ("xml" in ct) or ("rss" in ct) or ("atom" in ct) or ("application/octet-stream" in ct)

for ln in sys.stdin:
    ln = ln.strip()
    if not ln:
        continue
    try:
        item = json.loads(ln)
    except Exception:
        continue

    url = item.get("url","")
    out = dict(item)
    out["checked_by"] = "feed_eval_v1"
    out["ok"] = False
    out["status"] = 0
    out["content_type"] = ""
    out["reason"] = ""

    if not url or not isinstance(url,str):
        out["reason"] = "no_url"
        print(json.dumps(out, ensure_ascii=False))
        continue

    rc, raw, err = curl_fetch(url)
    if rc != 0:
        out["reason"] = "curl_error"
        out["error"] = (err or "")[:300]
        print(json.dumps(out, ensure_ascii=False))
        continue

    headers, body = split_headers_body(raw)
    status = parse_status(headers)
    ct = header_value(headers, "Content-Type")
    out["status"] = status
    out["content_type"] = ct

    if status < 200 or status >= 300:
        out["reason"] = "http_status"
        print(json.dumps(out, ensure_ascii=False))
        continue

    # size guard (text length approx; curl already max-filesize, but keep)
    if len(body.encode("utf-8", errors="ignore")) > MAX_BYTES:
        out["reason"] = "too_large"
        print(json.dumps(out, ensure_ascii=False))
        continue

    # heuristic feed detection
    if (is_xmlish(ct) or body.lstrip().startswith("<")) and looks_like_feed(body):
        out["ok"] = True
        out["reason"] = "feed_ok"
    else:
        out["reason"] = "not_feed"

    print(json.dumps(out, ensure_ascii=False))

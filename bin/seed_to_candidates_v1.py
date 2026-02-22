#!/usr/bin/env python3
import json, sys, urllib.parse, datetime
from pathlib import Path

def now_utc_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def make_google_news_rss(q: str, hl: str, gl: str, ceid: str) -> str:
    # Google News RSS search endpoint
    # https://news.google.com/rss/search?q=...&hl=..&gl=..&ceid=..
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": q,
        "hl": hl,
        "gl": gl,
        "ceid": ceid
    })

def main():
    if len(sys.argv) != 3:
        print("usage: seed_to_candidates_v1.py <seed_json> <out_queue_jsonl>", file=sys.stderr)
        sys.exit(2)

    seed_path = Path(sys.argv[1])
    out_path  = Path(sys.argv[2])

    seed = json.loads(seed_path.read_text(encoding="utf-8"))

    # seed 형식:
    # { "v":1, "group":"...", "queries":[ {category_id, category_slug, q, hl, gl, ceid, source?}, ... ] }
    queries = seed.get("queries") or seed.get("items") or []
    if not isinstance(queries, list):
        raise SystemExit("seed.queries must be list")

    seen = set()
    lines = []
    for it in queries:
        if not isinstance(it, dict):
            continue
        cid  = it.get("category_id")
        slug = it.get("category_slug")
        q    = it.get("q") or it.get("query")
        hl   = it.get("hl") or "en-US"
        gl   = it.get("gl") or "US"
        ceid = it.get("ceid") or ("US:en" if hl.startswith("en") else "KR:ko")
        src  = it.get("source") or "google_news_rss_search"

        if cid is None or slug is None or not q:
            continue

        url = make_google_news_rss(q, hl, gl, ceid)

        key = url.strip()
        if key in seen:
            continue
        seen.add(key)

        rec = {
            "v": 1,
            "kind": "candidate_feed",
            "category_id": cid,
            "category_slug": slug,
            "source": src,
            "query": q,
            "url": url,
            "score": float(it.get("score", 0.9)),
            "utc": now_utc_iso(),
        }
        lines.append(json.dumps(rec, ensure_ascii=False))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(json.dumps({"ok": True, "candidates_written": len(lines)}, ensure_ascii=False))

if __name__ == "__main__":
    main()

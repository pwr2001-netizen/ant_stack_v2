#!/usr/bin/env python3
import os, json, subprocess, datetime, hashlib

UTC = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

INQ   = "registry/retest/retest_queue.jsonl"
DONE  = "registry/retest_done/retest_done.jsonl"
LOG   = "logs/retest_apply.log"

def append(path, recs):
    if not recs:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as w:
        for r in recs:
            w.write(json.dumps(r, ensure_ascii=False) + "\n")

def check_url(url: str, timeout=12):
    p = subprocess.run(["curl","-I","-L","--max-time",str(timeout),url], capture_output=True, text=True)
    out = p.stdout or ""
    low = out.lower()
    status = out.splitlines()[0].strip() if out.splitlines() else ""
    ctype = ""
    for ln in out.splitlines():
        if ln.lower().startswith("content-type:"):
            ctype = ln.split(":",1)[1].strip()
            break
    ok = (" 200" in status) and (("xml" in low) or ("rss" in low))
    return ok, status, ctype

def group_slug_to_groupname(category_slug: str):
    # 현재 구조: group 파일명이 seed_queries_market_us / seed_queries_market_kr
    # slug 기준으로 매핑이 필요하면 여기서 확장 가능.
    # 지금은 category_id로 추정하지 않고, record에 category_slug만 사용하고
    # out 파일은 "seed_queries_market_us/kr"로 나뉘지 않아도 되게, category_slug 기반으로 분기 가능.
    # 하지만 기존 파일 네이밍과 맞추기 위해 "market_us/kr"로 단순 매핑:
    # - us_market, global_* , fed_policy, crypto_market, commodities, earnings, global_investing => market_us
    # - kr_market => market_kr
    if category_slug == "kr_market":
        return "seed_queries_market_kr"
    return "seed_queries_market_us"

def prob_path(groupname):  # retest pass -> probation
    return f"registry/probation/probation_feeds_{groupname}.jsonl"

def tomb_path(groupname):  # retest fail -> tombstone
    return f"registry/tombstone/tombstone_feeds_{groupname}.jsonl"

if not os.path.exists(INQ):
    print("ok: true")
    print("reason: no_retest_queue")
    raise SystemExit(0)

lines = [ln.strip() for ln in open(INQ,"r",encoding="utf-8") if ln.strip()]
if not lines:
    print("ok: true")
    print("reason: empty_retest_queue")
    raise SystemExit(0)

passed = 0
failed = 0
done_recs = []
log_recs  = []

for ln in lines:
    try:
        x = json.loads(ln)
    except:
        continue

    url = x.get("url","")
    if not url:
        continue

    cid = x.get("category_id")
    slug = x.get("category_slug","")
    groupname = group_slug_to_groupname(slug)

    ok, status, ctype = check_url(url)

    rec = {
        "v": 1,
        "checked_utc": UTC,
        "kind": "retest_feed",
        "ok": ok,
        "status": status,
        "content_type": ctype,
        "url": url,
        "category_id": cid,
        "category_slug": slug,
        "source": x.get("source","tombstone_retest"),
        "score": x.get("score",0.1)
    }

    # 결과 기록
    if ok:
        append(prob_path(groupname), [rec])
        passed += 1
        rec["decision"] = "to_probation"
    else:
        append(tomb_path(groupname), [rec])
        failed += 1
        rec["decision"] = "stay_tombstone"

    done_recs.append(rec)
    log_recs.append(rec)

append(DONE, done_recs)
append(LOG, log_recs)

# queue 비우기
open(INQ, "w", encoding="utf-8").write("")

print("ok: true")
print("retest_in:", len(lines))
print("passed:", passed)
print("failed:", failed)

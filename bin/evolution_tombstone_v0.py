#!/usr/bin/env python3
import os, glob, json, datetime
from collections import defaultdict

UTC = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

TOMB_PAT = "registry/tombstone/tombstone_feeds_*.jsonl"
STATE_OUT = "registry/evolution/tombstone_state.jsonl"
PERM_OUT  = "registry/tombstone/tombstone_permanent.jsonl"
RETEST_OUT= "registry/retest/retest_queue.jsonl"

FAIL_STREAK_PERMANENT = 5

def load_latest_state(path):
    # latest record per url
    latest = {}
    if not os.path.exists(path):
        return latest
    with open(path,"r",encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: 
                continue
            try:
                x=json.loads(line)
            except:
                continue
            url=x.get("url")
            if url:
                latest[url]=x
    return latest

def append_jsonl(path, recs):
    if not recs:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path,"a",encoding="utf-8") as w:
        for r in recs:
            w.write(json.dumps(r, ensure_ascii=False) + "\n")

latest = load_latest_state(STATE_OUT)
fails = defaultdict(int)
meta  = {}

# init from latest
for url, st in latest.items():
    fails[url] = int(st.get("fails",0))
    meta[url] = st

# scan tombstone inputs
inputs = sorted(glob.glob(TOMB_PAT))
new_state=[]
new_perm=[]
new_retest=[]

tomb_urls=set()

for fp in inputs:
    with open(fp,"r",encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: 
                continue
            try:
                x=json.loads(line)
            except:
                continue
            url=x.get("url")
            if not url:
                continue
            if x.get("ok") is True:
                continue
            tomb_urls.add(url)
            fails[url] += 1
            meta[url] = {
                "v":1,
                "utc":UTC,
                "url":url,
                "fails":fails[url],
                "last_status":x.get("status",""),
                "last_content_type":x.get("content_type",""),
                "state":"tombstone"
            }
            # keep category info for retest
            meta[url]["category_id"] = x.get("category_id")
            meta[url]["category_slug"] = x.get("category_slug")

# decide actions
for url in sorted(tomb_urls):
    st = meta[url]
    if fails[url] >= FAIL_STREAK_PERMANENT:
        perm = {"v":1,"utc":UTC,"url":url,"reason":f"fail_streak>={FAIL_STREAK_PERMANENT}","fails":fails[url]}
        new_perm.append(perm)
        st2 = dict(st)
        st2["state"]="permanent"
        new_state.append(st2)
    else:
        # retest candidate
        rq = {
            "v":1,"utc":UTC,"kind":"retest_feed",
            "url":url,
            "category_id":st.get("category_id"),
            "category_slug":st.get("category_slug"),
            "source":"tombstone_retest",
            "score":0.10
        }
        new_retest.append(rq)
        new_state.append(st)

append_jsonl(STATE_OUT, new_state)
append_jsonl(PERM_OUT, new_perm)
append_jsonl(RETEST_OUT, new_retest)

print("ok: true")
print("tomb_inputs:", len(inputs))
print("tomb_urls:", len(tomb_urls))
print("retest_written:", len(new_retest))
print("permanent_written:", len(new_perm))

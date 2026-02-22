#!/usr/bin/env python3
import json, os, sys, datetime

UTC = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

CAT_FILE = sys.argv[1]
OUT_US   = sys.argv[2]
OUT_KR   = sys.argv[3]

cats = json.load(open(CAT_FILE,"r",encoding="utf-8")).get("categories",[])

def load_seed(p):
    if os.path.exists(p):
        x=json.load(open(p,"r",encoding="utf-8"))
    else:
        x={"version":"1.0","type":"seed_queries_group","updated_utc":UTC,"queries":[]}
    if "queries" not in x or not isinstance(x["queries"],list):
        x["queries"]=[]
    return x

def save_seed(p,x):
    x["updated_utc"]=UTC
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(x, open(p,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

def key(q):
    return (q.get("category_id"), q.get("category_slug"), q.get("lang"), q.get("query"))

us = load_seed(OUT_US)
kr = load_seed(OUT_KR)

exist=set(key(q) for q in us["queries"]+kr["queries"] if isinstance(q,dict))

def add_seed(seed_obj, cid, slug, lang, query):
    q={"category_id":cid,"category_slug":slug,"query":query,"lang":lang}
    k=key(q)
    if k in exist:
        return 0
    seed_obj["queries"].append(q)
    exist.add(k)
    return 1

added_us=0
added_kr=0

for c in cats:
    cid=c["id"]; slug=c["slug"]; g=c.get("group","")
    name_en=c.get("name_en",slug.replace("_"," "))
    name_ko=c.get("name_ko",slug)

    if g=="market_us" or cid<200:
        # US 그룹: 영어 query 2개
        added_us += add_seed(us, cid, slug, "en", f"{name_en} news")
        added_us += add_seed(us, cid, slug, "en", f"latest {name_en} update")
    elif g=="market_kr" or (200<=cid<300):
        # KR 그룹: 한국어 query 2개 + 1개는 영문(글로벌 검색 대비)
        added_kr += add_seed(kr, cid, slug, "ko", f"{name_ko} 뉴스")
        added_kr += add_seed(kr, cid, slug, "ko", f"최신 {name_ko} 소식")
        added_kr += add_seed(kr, cid, slug, "en", f"{name_en} Korea news")

save_seed(OUT_US, us)
save_seed(OUT_KR, kr)

print("ok: true")
print("added_us:", added_us, "total_us:", len(us["queries"]))
print("added_kr:", added_kr, "total_kr:", len(kr["queries"]))

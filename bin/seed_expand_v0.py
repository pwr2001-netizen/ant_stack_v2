#!/usr/bin/env python3
import os, json, glob, random, datetime, sys

UTC = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

# 기본 타깃 그룹
GROUP_US = "registry/seeds/groups/seed_queries_market_us.json"
GROUP_KR = "registry/seeds/groups/seed_queries_market_kr.json"

# 자동 선택 개수 (기본 10)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10

# 카테고리 파일 후보 경로들 (프로젝트 구조 차이 대비)
CANDIDATES = [
    "registry/categories/categories_v1.json",
    "registry/categories/categories_v1.0.json",
    "registry/categories_v1.json",
    "registry/categories.json",
    "registry/taxonomy/categories_v1.json",
    "registry/taxonomy/categories.json",
]

def find_categories_file():
    for p in CANDIDATES:
        if os.path.exists(p):
            return p
    # 마지막 수단: registry 아래 json 중 categories 들어간 파일
    hits = []
    for p in glob.glob("registry/**/*.json", recursive=True):
        name = os.path.basename(p).lower()
        if "categor" in name:
            hits.append(p)
    return hits[0] if hits else None

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path,"r",encoding="utf-8") as f:
        return json.load(f)

def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path,"w",encoding="utf-8") as w:
        json.dump(obj, w, ensure_ascii=False, indent=2)

def normalize_categories(cat_obj):
    # 허용 포맷:
    # 1) {"categories":[{"category_id":101,"category_slug":"us_market","name_en":"..."}...]}
    # 2) [{"category_id":...}, ...]
    if isinstance(cat_obj, dict) and "categories" in cat_obj:
        arr = cat_obj["categories"]
    elif isinstance(cat_obj, list):
        arr = cat_obj
    else:
        arr = []
    out=[]
    for x in arr:
        if not isinstance(x, dict):
            continue
        cid = x.get("category_id")
        slug = x.get("category_slug")
        if cid is None or slug is None:
            continue
        out.append({"category_id": int(cid), "category_slug": str(slug)})
    return out

def load_group(path):
    base = {
        "version":"1.0",
        "type":"seed_queries_group",
        "group": os.path.basename(path).replace(".json",""),
        "updated_utc": UTC,
        "queries":[]
    }
    obj = load_json(path, base)
    if "queries" not in obj or not isinstance(obj["queries"], list):
        obj["queries"] = []
    obj["updated_utc"] = UTC
    return obj

def existing_slugs(group):
    s=set()
    for q in group.get("queries",[]):
        if isinstance(q, dict) and "category_slug" in q:
            s.add(q["category_slug"])
    return s

def choose_new(categories, existing, n):
    pool=[c for c in categories if c["category_slug"] not in existing]
    random.shuffle(pool)
    return pool[:n]

def make_query(slug):
    # 최소 안전 쿼리: 구체적 단어를 넣되 너무 좁히지 않음
    # (나중에 고도화 가능: slug별 템플릿)
    # 한국 관련 slug는 ko seed도 만들 수 있지만, 여기선 그룹별 분기에서 결정
    base = slug.replace("_"," ")
    return f"{base} news"

def is_kr_category(slug):
    # 현재는 kr_market만 KR 그룹으로 분리
    # (추후 200대 전체가 들어오면 규칙 확장)
    return slug.startswith("kr_") or slug in {"kr_market","kospi_kosdaq","kr_bonds","kr_policy_market"}

def append_queries(group, picks, lang):
    # 중복 방지
    seen = {(q.get("category_id"), q.get("category_slug"), q.get("query"), q.get("lang"))
            for q in group.get("queries",[]) if isinstance(q, dict)}
    added=0
    for c in picks:
        cid=c["category_id"]; slug=c["category_slug"]
        qtxt = make_query(slug)
        rec = {"category_id": cid, "category_slug": slug, "query": qtxt, "lang": lang}
        key=(cid,slug,qtxt,lang)
        if key in seen:
            continue
        group["queries"].append(rec)
        seen.add(key)
        added += 1
    return added

def main():
    cat_file = find_categories_file()
    if not cat_file:
        print("ok: false")
        print("reason: categories_file_not_found")
        sys.exit(2)

    cats_raw = load_json(cat_file, {})
    cats = normalize_categories(cats_raw)

    us = load_group(GROUP_US)
    kr = load_group(GROUP_KR)

    ex_us = existing_slugs(us)
    ex_kr = existing_slugs(kr)
    ex_all = ex_us | ex_kr

    picks = choose_new(cats, ex_all, N)

    picks_us = [c for c in picks if not is_kr_category(c["category_slug"])]
    picks_kr = [c for c in picks if is_kr_category(c["category_slug"])]

    added_us = append_queries(us, picks_us, "en")
    added_kr = append_queries(kr, picks_kr, "ko")

    save_json(GROUP_US, us)
    save_json(GROUP_KR, kr)

    print("ok: true")
    print("categories_file:", cat_file)
    print("picked_total:", len(picks))
    print("picked_us:", len(picks_us), "added_us:", added_us)
    print("picked_kr:", len(picks_kr), "added_kr:", added_kr)
    print("group_us:", GROUP_US)
    print("group_kr:", GROUP_KR)

if __name__ == "__main__":
    main()

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p scouts/inbox scouts/outbox scouts/candidates registry/candidates registry/probation registry/tombstone registry/feeds registry/probation_done logs

# A) seed_queries -> inbox/outbox/candidates -> candidate queue (overwrite)
rm -f scouts/inbox/*.jsonl scouts/outbox/*.jsonl scouts/candidates/*.jsonl
: > registry/candidates/candidate_feeds_queue.jsonl

python3 -c $'import json,os,glob,hashlib,urllib.parse\nq=json.load(open("registry/seeds/seed_queries_v1.json","r",encoding="utf-8"))["queries"]\nos.makedirs("scouts/inbox",exist_ok=True)\nos.makedirs("scouts/outbox",exist_ok=True)\nos.makedirs("scouts/candidates",exist_ok=True)\nfor x in q:\n  cid=x["category_id"]; slug=x["category_slug"]; query=x["query"]; lang=x.get("lang","en")\n  inbox={"v":1,"kind":"seed_query","category_id":cid,"category_slug":slug,"query":query,"lang":lang}\n  open("scouts/inbox/%s_%s.jsonl"%(cid,slug),"w",encoding="utf-8").write(json.dumps(inbox,ensure_ascii=False)+"\\n")\n  job={"v":1,"kind":"discover_rss_by_query","category_id":cid,"category_slug":slug,"query":query,"lang":lang,"engine":"google_news_rss","created_utc":"2026-02-19T00:00:00Z"}\n  b=json.dumps(job,sort_keys=True,separators=(",",":")).encode("utf-8")\n  job["job_id"]=hashlib.sha1(b).hexdigest()[:16]\n  open("scouts/outbox/%s_%s.jsonl"%(cid,slug),"w",encoding="utf-8").write(json.dumps(job,ensure_ascii=False)+"\\n")\n  if lang=="ko":\n    hl,gl,ceid="ko","KR","KR:ko"\n  else:\n    hl,gl,ceid="en-US","US","US:en"\n  url="https://news.google.com/rss/search?q=%s&hl=%s&gl=%s&ceid=%s"%(urllib.parse.quote(query),hl,gl,ceid)\n  cand={"v":1,"kind":"candidate_feed","category_id":cid,"category_slug":slug,"source":"google_news_rss_search","query":query,"url":url,"score":0.90}\n  open("scouts/candidates/%s_%s.jsonl"%(cid,slug),"w",encoding="utf-8").write(json.dumps(cand,ensure_ascii=False)+"\\n")\n'
cat scouts/candidates/*.jsonl > registry/candidates/candidate_feeds_queue.jsonl

# B) candidate queue -> probation/tombstone (fresh overwrite)
: > registry/probation/probation_feeds.jsonl
: > registry/tombstone/tombstone_feeds.jsonl

python3 -c 'import json,subprocess; INP="registry/candidates/candidate_feeds_queue.jsonl"; OKO="registry/probation/probation_feeds.jsonl"; BADO="registry/tombstone/tombstone_feeds.jsonl"; LOG="logs/feed_check.log"; passed=failed=0;
for line in open(INP,"r",encoding="utf-8"):
  line=line.strip()
  if not line: 
    continue
  item=json.loads(line); url=item["url"]
  p=subprocess.run(["curl","-I","-L","--max-time","12",url],capture_output=True,text=True)
  out=p.stdout or ""; low=out.lower()
  status=(out.splitlines()[0].strip() if out.splitlines() else "")
  ctype=""
  for ln in out.splitlines():
    if ln.lower().startswith("content-type:"):
      ctype=ln.split(":",1)[1].strip(); break
  ok=(" 200" in status) and (("xml" in low) or ("rss" in low))
  rec={"v":1,"checked_utc":"2026-02-19T00:00:00Z","ok":ok,"status":status,"content_type":ctype,**item}
  of=OKO if ok else BADO
  open(of,"a",encoding="utf-8").write(json.dumps(rec,ensure_ascii=False)+"\n")
  open(LOG,"a",encoding="utf-8").write(json.dumps(rec,ensure_ascii=False)+"\n")
  passed+=1 if ok else 0
  failed+=0 if ok else 1
print("ok: true"); print("passed:",passed); print("failed:",failed)'

# C) probation -> feeds_registry append (dedupe), probation -> done, clear probation
python3 -c 'import json,os,hashlib;
INP="registry/probation/probation_feeds.jsonl"; OUT="registry/feeds/feeds_registry.jsonl"; DONE="registry/probation_done/probation_feeds_done.jsonl";
os.makedirs("registry/feeds",exist_ok=True); os.makedirs("registry/probation_done",exist_ok=True)
def fid(url): return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
existing=set()
if os.path.exists(OUT):
  for line in open(OUT,"r",encoding="utf-8"):
    line=line.strip()
    if not line: continue
    try:
      x=json.loads(line); u=x.get("url"); 
      if u: existing.add(u)
    except: pass
added=0; skipped=0; buf=[]
if os.path.exists(INP):
  for line in open(INP,"r",encoding="utf-8"):
    line=line.strip()
    if not line: continue
    x=json.loads(line); url=x["url"]
    if url in existing: skipped+=1; continue
    buf.append({"v":1,"kind":"feed","feed_id":fid(url),"category_id":x["category_id"],"category_slug":x["category_slug"],"url":url,"source":x.get("source",""),"score":x.get("score",0.0),"status":"active"})
    existing.add(url); added+=1
if buf:
  with open(OUT,"a",encoding="utf-8") as w:
    for rec in buf: w.write(json.dumps(rec,ensure_ascii=False)+"\n")
txt=open(INP,"r",encoding="utf-8").read() if os.path.exists(INP) else ""
if txt.strip():
  with open(DONE,"a",encoding="utf-8") as w: w.write(txt if txt.endswith("\n") else txt+"\n")
open(INP,"w",encoding="utf-8").write("")
print("ok: true"); print("added:",added); print("skipped:",skipped)'

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, json, os
from datetime import datetime, timezone

V=1
DEFAULT_HISTORY_DIR="var/registrar/probation_history"

def now_iso_utc()->str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def json_dump(o)->str:
    return json.dumps(o, ensure_ascii=False, separators=(",",":"), sort_keys=True)

def safe_write_json(path:str, obj)->None:
    tmp=path+".tmp"
    with open(tmp,"w",encoding="utf-8") as f:
        f.write(json_dump(obj)); f.write("\n")
    os.replace(tmp,path)

def load_json(path:str):
    with open(path,"r",encoding="utf-8") as f:
        return json.load(f)

def clamp01(x):
    try: x=float(x)
    except Exception: return None
    if x<0: x=0.0
    if x>1: x=1.0
    return x

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("evaluator_json")
    ap.add_argument("--history-dir", default=DEFAULT_HISTORY_DIR)
    ap.add_argument("--dry-run", action="store_true")
    args=ap.parse_args()

    out={"v":V,"action":"probation_update","ok":True,"ts":now_iso_utc(),
         "input":{"evaluator_json":args.evaluator_json},
         "paths":{"history_dir":args.history_dir},
         "result":{"history_file":None,"updated":False},
         "error":None}
    try:
        ev=load_json(args.evaluator_json)
        if not isinstance(ev,dict):
            raise ValueError("evaluator_json must be dict")

        canonical=(ev.get("canonical_url") or "").strip()
        sha1=(ev.get("sha1") or "").strip()
        metrics=ev.get("metrics") or {}

        if not sha1 and not canonical:
            raise ValueError("need sha1 or canonical_url")

        rec={"canonical_url":canonical,"sha1":sha1,"ts":(ev.get("ts") or now_iso_utc()),
             "metrics":{
                 "valid_ratio":clamp01(metrics.get("valid_ratio")),
                 "error_rate":clamp01(metrics.get("error_rate")),
                 "dup_ratio":clamp01(metrics.get("dup_ratio")),
                 "items_count":metrics.get("items_count"),
             }}

        os.makedirs(args.history_dir, exist_ok=True)
        key=(sha1 or canonical).replace("/","_").replace(":","_")
        hist_path=os.path.join(args.history_dir, f"{key}.json")
        out["result"]["history_file"]=hist_path

        hist={"v":1,"action":"probation_history","ok":True,"sha1":sha1,"canonical_url":canonical,"events":[]}
        if os.path.exists(hist_path):
            try:
                old=load_json(hist_path)
                if isinstance(old,dict) and isinstance(old.get("events"),list):
                    hist=old
            except Exception:
                pass

        hist.setdefault("events", []).append(rec)
        if len(hist["events"])>200:
            hist["events"]=hist["events"][-200:]
        hist["ts"]=now_iso_utc()
        hist["ok"]=True
        if sha1: hist["sha1"]=sha1
        if canonical: hist["canonical_url"]=canonical

        if not args.dry_run:
            safe_write_json(hist_path, hist)

        out["result"]["updated"]=True

    except Exception as e:
        out["ok"]=False
        out["error"]={"code":"exception","message":str(e)}

    print(json_dump(out))
    return 0 if out["ok"] else 2

if __name__=="__main__":
    raise SystemExit(main())

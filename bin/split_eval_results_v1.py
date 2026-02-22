#!/usr/bin/env python3
import sys, json, os

if len(sys.argv) != 3:
    print("usage: split_eval_results_v1.py PROB.jsonl TOMB.jsonl", file=sys.stderr)
    sys.exit(2)

prob_path = sys.argv[1]
tomb_path = sys.argv[2]
os.makedirs(os.path.dirname(prob_path) or ".", exist_ok=True)
os.makedirs(os.path.dirname(tomb_path) or ".", exist_ok=True)

p_ok = 0
t_ok = 0

with open(prob_path, "w", encoding="utf-8") as fp, open(tomb_path, "w", encoding="utf-8") as ft:
    for ln in sys.stdin:
        ln = ln.strip()
        if not ln:
            continue
        try:
            x = json.loads(ln)
        except Exception:
            continue
        if x.get("ok") is True:
            fp.write(json.dumps(x, ensure_ascii=False) + "\n")
            p_ok += 1
        elif x.get("ok") is False:
            ft.write(json.dumps(x, ensure_ascii=False) + "\n")
            t_ok += 1

print(f"ok: true\nprobation: {p_ok}\ntombstone: {t_ok}")

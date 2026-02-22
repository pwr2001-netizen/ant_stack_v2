#!/usr/bin/env python3
import sys, json
from pathlib import Path

def main():
    if len(sys.argv) != 3:
        print("usage: split_eval_v1.py <probation_jsonl> <tombstone_jsonl>", file=sys.stderr)
        sys.exit(2)

    prob_path = Path(sys.argv[1])
    tomb_path = Path(sys.argv[2])
    prob_path.parent.mkdir(parents=True, exist_ok=True)
    tomb_path.parent.mkdir(parents=True, exist_ok=True)

    p = 0
    t = 0
    with prob_path.open("w", encoding="utf-8") as fp, tomb_path.open("w", encoding="utf-8") as ft:
        for ln in sys.stdin:
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except Exception:
                continue
            ok = obj.get("ok")
            if ok is True:
                fp.write(ln + "\n")
                p += 1
            elif ok is False:
                ft.write(ln + "\n")
                t += 1

    print(json.dumps({"ok": True, "probation": p, "tombstone": t}, ensure_ascii=False))

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import json, sys, datetime
from pathlib import Path

def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def main():
    # args: <runlog_path> <group> <seed> <candidates> <passed> <failed> <added> <skipped>
    if len(sys.argv) != 9:
        print("usage: append_runlog_v1.py <runlog> <group> <seed> <candidates> <passed> <failed> <added> <skipped>", file=sys.stderr)
        sys.exit(2)

    runlog = Path(sys.argv[1])
    runlog.parent.mkdir(parents=True, exist_ok=True)

    rec = {
        "v": 1,
        "utc": now_utc(),
        "group": sys.argv[2],
        "seed": sys.argv[3],
        "decision": "ok",
        "candidates": int(sys.argv[4]),
        "passed": int(sys.argv[5]),
        "failed": int(sys.argv[6]),
        "added": int(sys.argv[7]),
        "skipped": int(sys.argv[8]),
    }
    with runlog.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps({"ok": True}, ensure_ascii=False))

if __name__ == "__main__":
    main()

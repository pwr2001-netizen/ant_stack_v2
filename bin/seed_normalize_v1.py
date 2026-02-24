#!/usr/bin/env python3
import json, sys
from pathlib import Path

def main():
    if len(sys.argv) != 3:
        print(json.dumps({"ok": False, "reason": "usage", "usage": "seed_normalize_v1.py <in_seed_json> <out_seed_json>"}))
        return 2

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    if not in_path.exists():
        print(json.dumps({"ok": False, "reason": "input_missing", "path": str(in_path)}))
        return 2

    obj = json.loads(in_path.read_text(encoding="utf-8"))

    # allow either dict wrapper or raw list
    queries = None
    if isinstance(obj, dict):
        queries = obj.get("queries") or obj.get("items") or []
    elif isinstance(obj, list):
        queries = obj
    else:
        print(json.dumps({"ok": False, "reason": "bad_type", "type": type(obj).__name__}))
        return 2

    norm = []
    dropped = 0

    for x in queries:
        # case A: URL string
        if isinstance(x, str):
            u = x.strip()
            if not u:
                dropped += 1
                continue
            norm.append({
                "source": "seed_manual",
                "queries": [u]
            })
            continue

        # case B: dict item - pass through (ensure minimal fields)
        if isinstance(x, dict):
            item = dict(x)
            if "queries" not in item and "items" not in item:
                # best effort: if it has q/query/url, turn into queries list
                for k in ("query", "q", "url"):
                    if k in item and isinstance(item[k], str) and item[k].strip():
                        item["queries"] = [item[k].strip()]
                        break
            if "source" not in item:
                item["source"] = "seed_manual"
            norm.append(item)
            continue

        # otherwise drop
        dropped += 1

    out_obj = {"queries": norm}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"ok": True, "in": str(in_path), "out": str(out_path), "in_count": len(queries), "out_count": len(norm), "dropped": dropped}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

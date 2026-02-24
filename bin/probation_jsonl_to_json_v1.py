#!/usr/bin/env python3
import json, sys
from pathlib import Path

def main():
    if len(sys.argv) != 3:
        print(json.dumps({"ok": False, "reason": "usage", "usage": "probation_jsonl_to_json_v1.py <in_probation_jsonl> <out_json>"}))
        return 2

    inp = Path(sys.argv[1])
    out = Path(sys.argv[2])

    if not inp.exists():
        print(json.dumps({"ok": False, "reason": "input_missing", "path": str(inp)}))
        return 2

    rows=[]
    bad=0
    for line in inp.read_text(encoding="utf-8", errors="replace").splitlines():
        line=line.strip()
        if not line:
            continue
        try:
            obj=json.loads(line)
        except Exception:
            bad += 1
            continue
        # registrar가 url을 찾을 수 있게 최소 url 키 보장
        url = obj.get("url") or obj.get("canonical_url")
        if not url:
            bad += 1
            continue
        # registrar 호환 최소형
        rows.append({"url": url, "canonical_url": url, **obj})

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""), encoding="utf-8")

    print(json.dumps({"ok": True, "in": str(inp), "out": str(out), "rows": len(rows), "bad": bad}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

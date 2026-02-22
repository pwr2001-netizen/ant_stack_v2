#!/usr/bin/env python3
import json, time
from pathlib import Path

def now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")

def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    spec_path = Path("config/registrar_apply_spec.json")
    if not spec_path.exists():
        res = {"ok": False, "ts": now_ts(), "action": "registrar_apply", "error": "spec_missing", "path": str(spec_path)}
        print(json.dumps(res, ensure_ascii=False))
        return 0

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    inp = spec.get("input", {})
    plan_path = Path(inp.get("plan_json", "var/registrar/runlog/compile_plan.json"))
    out_runlog = Path(inp.get("out_runlog_json", "var/registrar/runlog/apply_result.json"))
    mode = inp.get("mode", "apply")

    if not plan_path.exists():
        res = {"ok": False, "ts": now_ts(), "action": "registrar_apply", "error": "plan_missing", "plan": str(plan_path)}
        write_json(out_runlog, res)
        print(json.dumps(res, ensure_ascii=False))
        return 0

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    ops = plan.get("ops", []) if isinstance(plan, dict) else []

    res = {
        "v": 1,
        "ts": now_ts(),
        "action": "registrar_apply",
        "ok": True,
        "mode": mode,
        "counts": {"ops_total": len(ops), "applied": 0, "skipped": 0, "errors": 0},
        "notes": []
    }

    for op in ops:
        if not isinstance(op, dict):
            res["counts"]["skipped"] += 1
            continue
        if op.get("op") != "add_active":
            res["counts"]["skipped"] += 1
            continue

        src = Path(op.get("src", ""))
        dst = Path(op.get("dst", ""))
        url = op.get("url")
        if not src or not dst or not url:
            res["counts"]["errors"] += 1
            res["notes"].append({"op": "error", "reason": "missing_fields", "detail": op})
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            res["counts"]["skipped"] += 1
            continue

        entry = {
            "v": 1,
            "ts": now_ts(),
            "status": "active",
            "url": url,
            "source_probation_file": str(src)
        }
        dst.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
        res["counts"]["applied"] += 1

    write_json(out_runlog, res)
    print(json.dumps({"ok": True, "out": str(out_runlog), "counts": res["counts"]}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

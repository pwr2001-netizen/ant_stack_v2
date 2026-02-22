#!/usr/bin/env python3
import json, time, hashlib
from pathlib import Path

def now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")

def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def load_json(path: Path):
    try:
        return True, json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, str(e)

def load_tombstone_index(tomb_dir: Path):
    idx = tomb_dir / "index.json"
    if not idx.exists():
        return set()
    ok, obj = load_json(idx)
    if not ok or not isinstance(obj, dict):
        return set()
    items = obj.get("items")
    if not isinstance(items, list):
        return set()
    out = set()
    for x in items:
        if isinstance(x, str) and x:
            out.add(x)
    return out

def main():
    spec_path = Path("config/registrar_spec.json")
    if not spec_path.exists():
        print(json.dumps({"ok": False, "error": "spec_missing", "path": str(spec_path)}, ensure_ascii=False))
        return 0

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    inp = spec.get("input", {})
    probation_dir = Path(inp.get("probation_dir", "var/discovery/probation"))
    active_dir = Path(inp.get("active_dir", "var/registrar/active"))
    tomb_dir = Path(inp.get("tombstone_dir", "var/registrar/tombstone"))
    out_plan = Path(inp.get("out_plan_json", "var/registrar/runlog/compile_plan.json"))

    if not probation_dir.exists():
        print(json.dumps({"ok": False, "error": "probation_dir_missing", "probation_dir": str(probation_dir)}, ensure_ascii=False))
        return 0

    active_dir.mkdir(parents=True, exist_ok=True)
    tomb_dir.mkdir(parents=True, exist_ok=True)
    out_plan.parent.mkdir(parents=True, exist_ok=True)

    files = sorted([p for p in probation_dir.rglob("*.json") if p.is_file()])

    tomb_set = load_tombstone_index(tomb_dir)


    plan = {
        "v": 1,
        "ts": now_ts(),
        "action": "registrar_compile",
        "ok": True,
        "counts": {"probation_files": len(files), "to_active": 0, "to_tombstone": 0, "skipped": 0},
        "ops": []
    }

    seen = set()
    for f in files:
        ok, obj = load_json(f)
        if not ok:
            plan["counts"]["skipped"] += 1
            plan["ops"].append({"op": "skip", "reason": "json_parse_error", "file": str(f), "detail": obj})
            continue

        url = None
        if isinstance(obj, dict):
            url = obj.get("canonical_url") or obj.get("url")

        if not url:
            plan["counts"]["skipped"] += 1
            plan["ops"].append({"op": "skip", "reason": "url_missing", "file": str(f)})
            continue

        key = sha1(url.strip())
        if key in tomb_set:
            plan["counts"]["skipped"] += 1
            plan["ops"].append({"op": "skip", "reason": "tombstoned_permanent", "url": url, "file": str(f)})
            continue

        if key in seen:
            plan["counts"]["skipped"] += 1
            plan["ops"].append({"op": "skip", "reason": "dup_in_probation_batch", "url": url, "file": str(f)})
            continue
        seen.add(key)

        active_path = active_dir / f"{key}.json"
        if active_path.exists():
            plan["counts"]["skipped"] += 1
            plan["ops"].append({"op": "skip", "reason": "already_active", "url": url, "dst": str(active_path)})
            continue

        plan["counts"]["to_active"] += 1
        plan["ops"].append({"op": "add_active", "url": url, "src": str(f), "dst": str(active_path)})

    out_plan.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "plan": str(out_plan), "counts": plan["counts"]}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

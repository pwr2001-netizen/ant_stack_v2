#!/usr/bin/env python3
import json, os, sys, subprocess, time
from pathlib import Path

def jprint(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")

def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent

def load_manifest(root: Path) -> dict:
    mf = root / "tools" / "manifest.json"
    if not mf.exists():
        return {"v": 1, "required_files": [], "min_bytes": {}}
    return json.loads(mf.read_text(encoding="utf-8"))

def file_size_ok(root: Path, rel: str, min_bytes: int) -> tuple[bool, str]:
    p = root / rel
    if not p.exists():
        return False, f"missing: {rel}"
    if p.is_dir():
        return True, f"dir_ok: {rel}"
    sz = p.stat().st_size
    if sz < min_bytes:
        return False, f"too_small: {rel} size={sz} < {min_bytes}"
    return True, f"ok: {rel} size={sz}"

def run_cmd(cmd: list[str], cwd: Path) -> tuple[int, str]:
    try:
        out = subprocess.check_output(cmd, cwd=str(cwd), stderr=subprocess.STDOUT)
        return 0, out.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        return e.returncode, (e.output or b"").decode("utf-8", errors="replace")

def iter_files(root: Path, exts: tuple[str, ...]) -> list[Path]:
    # 간단/결정적: git tracked 파일만 검사하면 더 정확하지만,
    # 여기서는 우선 로컬 트리에서 확장자 기준으로만 검사.
    files = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in exts and ".git" not in p.parts:
            files.append(p)
    return sorted(files)

def cmd_verify(root: Path) -> dict:
    mf = load_manifest(root)
    required = mf.get("required_files", [])
    minmap = mf.get("min_bytes", {})
    details = []
    ok = True

    for rel in required:
        mb = int(minmap.get(rel, 1))
        pass_ok, msg = file_size_ok(root, rel, mb)
        details.append({"file": rel, "ok": pass_ok, "msg": msg})
        if not pass_ok:
            ok = False

    return {
        "ok": ok,
        "stage": "verify",
        "required_count": len(required),
        "details": details
    }

def cmd_lint(root: Path) -> dict:
    details = []
    ok = True

    # bash syntax check
    sh_files = iter_files(root, (".sh",))
    for p in sh_files:
        code, out = run_cmd(["bash", "-n", str(p)], root)
        details.append({"kind": "bash", "file": str(p.relative_to(root)), "ok": code == 0, "msg": out.strip()[:4000]})
        if code != 0:
            ok = False

    # python compile check
    py_files = iter_files(root, (".py",))
    for p in py_files:
        code, out = run_cmd([sys.executable, "-m", "py_compile", str(p)], root)
        details.append({"kind": "py_compile", "file": str(p.relative_to(root)), "ok": code == 0, "msg": out.strip()[:4000]})
        if code != 0:
            ok = False

    return {
        "ok": ok,
        "stage": "lint",
        "checked": {"sh": len(sh_files), "py": len(py_files)},
        "details": details
    }

def cmd_test(root: Path) -> dict:
    # 프로젝트에 이미 있는 테스트 엔트리포인트가 있다면 여기서만 호출
    # 우선 bin/run_tests.sh가 있으면 실행
    test_sh = root / "bin" / "run_tests.sh"
    if not test_sh.exists():
        return {"ok": False, "stage": "test", "msg": "missing bin/run_tests.sh (create or point ctl.py to your test entrypoint)"}

    code, out = run_cmd(["bash", str(test_sh)], root)
    return {"ok": code == 0, "stage": "test", "exit_code": code, "output": out[-8000:]}

def cmd_run(root: Path, args: list[str]) -> dict:
    # 안전: verify+lint 통과 후에만 run 허용
    v = cmd_verify(root)
    if not v["ok"]:
        return {"ok": False, "stage": "run", "msg": "verify_failed", "verify": v}
    l = cmd_lint(root)
    if not l["ok"]:
        return {"ok": False, "stage": "run", "msg": "lint_failed", "lint": l}

    # subcommand routing
    # 사용 예:
    #   ctl.py run group
    #   ctl.py run tests
    #   ctl.py run smoke
    #   ctl.py run discovery
    #   ctl.py run batch
    sub = (args[0].lower() if args else "group")
    rest = args[1:] if args else []

    # run all: verify -> lint -> test -> discovery(group) -> registrar
    if sub == "all":
        # 1) tests
        t = cmd_test(root)
        if not t.get("ok", False):
            return {"ok": False, "stage": "run", "target": "all", "step": "test", "test": t}

        # 2) discovery group
        group_sh = root / "bin" / "run_discovery_group.sh"
        if not group_sh.exists():
            return {"ok": False, "stage": "run", "target": "all", "step": "group", "msg": "missing bin/run_discovery_group.sh"}
        # seed path: first arg after "all" (required)
        seed = rest[0] if rest else ""
        if (not seed) or (not (root / seed).exists() and not Path(seed).exists()):
            return {"ok": False, "stage": "run", "target": "all", "step": "group",
                    "msg": "seed_required", "usage": "ctl run all <seed_json_path>"}

        # allow both relative-to-repo and absolute paths
        seed_path = str((root / seed).resolve()) if (root / seed).exists() else str(Path(seed).resolve())

        cG, oG = run_cmd(["bash", str(group_sh), seed_path], root)
        if cG != 0:
            return {"ok": False, "stage": "run", "target": "all", "step": "group", "exit_code": cG, "output": oG[-8000:]}

        # 3) registrar
        compile_py = root / "ants" / "registrar" / "registrar_compile.py"
        apply_py = root / "ants" / "registrar" / "registrar_apply.py"
        if not compile_py.exists() or not apply_py.exists():
            return {"ok": False, "stage": "run", "target": "all", "step": "registrar",
                    "msg": "missing_registrar_files", "compile": str(compile_py), "apply": str(apply_py)}

        c1, o1 = run_cmd([sys.executable, str(compile_py)], root)
        if c1 != 0:
            return {"ok": False, "stage": "run", "target": "all", "step": "registrar_compile", "exit_code": c1, "output": o1[-8000:]}

        c2, o2 = run_cmd([sys.executable, str(apply_py)], root)
        out = (oG + "\n" + o1 + "\n" + o2)
        return {"ok": c2 == 0, "stage": "run", "target": "all", "step": "done", "exit_code": c2, "output": out[-8000:]}


    # registrar: python compile -> python apply (MUST NOT run via bash)
    if sub == "registrar":
        compile_py = root / "ants" / "registrar" / "registrar_compile.py"
        apply_py = root / "ants" / "registrar" / "registrar_apply.py"
        if not compile_py.exists() or not apply_py.exists():
            return {"ok": False, "stage": "run", "msg": "missing_registrar_files",
                    "compile": str(compile_py), "apply": str(apply_py)}

        c1, o1 = run_cmd([sys.executable, str(compile_py)] + rest, root)
        if c1 != 0:
            return {"ok": False, "stage": "run", "target": "registrar", "step": "compile",
                    "exit_code": c1, "output": o1[-8000:]}

        c2, o2 = run_cmd([sys.executable, str(apply_py)] + rest, root)
        out = (o1 + "\n" + o2)
        return {"ok": c2 == 0, "stage": "run", "target": "registrar", "step": "apply",
                "exit_code": c2, "output": out[-8000:]}

    routes = {
        "group": root / "bin" / "run_discovery_group.sh",
        "tests": root / "bin" / "run_tests.sh",
        "smoke": root / "bin" / "smoke.sh",
        "discovery": root / "bin" / "run_discovery.sh",
        "batch": root / "bin" / "run_discovery_batch.sh",
            "registrar": root / "ants" / "registrar" / "registrar_compile.py",
}

    entry = routes.get(sub)
    if entry is None:
        return {"ok": False, "stage": "run", "msg": "unknown_run_target", "target": sub, "allowed": sorted(routes.keys())}
    if not entry.exists():
        return {"ok": False, "stage": "run", "msg": "missing_entrypoint", "entry": str(entry)}

    code, out = run_cmd(["bash", str(entry)] + rest, root)
    return {"ok": code == 0, "stage": "run", "target": sub, "exit_code": code, "output": out[-8000:]}


def main():
    t0 = time.time()
    root = repo_root()

    if len(sys.argv) < 2:
        jprint({"ok": False, "msg": "usage: ctl.py [verify|lint|test|run] ..."})
        sys.exit(2)

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    if cmd == "verify":
        res = cmd_verify(root)
    elif cmd == "lint":
        res = cmd_lint(root)
    elif cmd == "test":
        res = cmd_test(root)
    elif cmd == "run":
        res = cmd_run(root, args)
    else:
        res = {"ok": False, "msg": f"unknown_command: {cmd}"}
        jprint(res)
        sys.exit(2)

    res["elapsed_ms"] = int((time.time() - t0) * 1000)
    jprint(res)
    sys.exit(0 if res.get("ok") else 1)

if __name__ == "__main__":
    main()

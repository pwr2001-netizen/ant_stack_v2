import json
import subprocess
import os

inp = "registry/candidates/candidate_feeds_queue.jsonl"
ok_out = "registry/probation/probation_feeds.jsonl"
bad_out = "registry/tombstone/tombstone_feeds.jsonl"
logp = "logs/feed_check.log"

def check_url(url):
    try:
        p = subprocess.run(
            ["curl", "-I", "-L", "--max-time", "12", url],
            capture_output=True,
            text=True
        )
        head = p.stdout.lower()
        status_line = p.stdout.splitlines()[0] if p.stdout else ""
        content_type = ""
        for line in p.stdout.splitlines():
            if line.lower().startswith("content-type:"):
                content_type = line.split(":", 1)[1].strip()
                break
        ok = (" 200" in status_line) and ("xml" in head or "rss" in head)
        return ok, status_line.strip(), content_type
    except Exception as e:
        return False, str(e), ""

if not os.path.exists(inp):
    print("no input file")
    exit()

passed = 0
failed = 0

with open(inp, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        ok, status, ctype = check_url(item["url"])

        record = {
            "v": 1,
            "ok": ok,
            "status": status,
            "content_type": ctype,
            **item
        }

        out_file = ok_out if ok else bad_out

        with open(out_file, "a", encoding="utf-8") as w:
            w.write(json.dumps(record, ensure_ascii=False) + "\n")

        with open(logp, "a", encoding="utf-8") as lw:
            lw.write(json.dumps(record, ensure_ascii=False) + "\n")

        if ok:
            passed += 1
        else:
            failed += 1

print("ok:", True)
print("passed:", passed)
print("failed:", failed)

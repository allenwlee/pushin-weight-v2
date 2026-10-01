"""Recover existing job receipts in small pages; never submit an inference call.

The original Render CLI --limit 100 collection timed out, while --limit 5
returned immediately. This transport-only helper preserves the frozen runner,
requests, rubric, and provider-call ledger.
"""
import base64
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import zlib

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("frozen_experiment", HERE / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def parse_stream(raw):
    decoder = json.JSONDecoder()
    rows = []
    remaining = raw.strip()
    while remaining:
        row, end = decoder.raw_decode(remaining)
        rows.append(row)
        remaining = remaining[end:].lstrip()
    return rows


job = run.read("job.json")
cursor = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
groups = {}
required = {"preflight", "complete"} | {f"{kind}_{i}" for kind in ("started", "finished") for i in range(4)}
for page in range(10):
    command = ["render", "logs", "--resources", job["id"], "--limit", "5",
               "--output", "json", "--direction", "backward", "--end", cursor]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()  # Only this helper's own read-only CLI child.
        stdout, stderr = process.communicate()
    run.save(f"log-recovery/page-{page:02}.json", {"command": command, "timed_out": timed_out,
             "returncode": process.returncode, "stdout": stdout, "stderr": stderr})
    rows = parse_stream(stdout)
    for row in rows:
        for kind, part, count, chunk in re.findall(r"PW_JEV_REVIEW ([a-z0-9_]+):(\d+)/(\d+):([A-Za-z0-9+/=]+)", row.get("message", "")):
            group = groups.setdefault(kind, {"count": int(count), "parts": {}})
            assert group["count"] == int(count)
            if int(part) in group["parts"]:
                assert group["parts"][int(part)] == chunk
            group["parts"][int(part)] = chunk
    complete = set()
    for kind, group in groups.items():
        if set(group["parts"]) != set(range(1, group["count"] + 1)):
            continue
        blob = "".join(group["parts"][i] for i in range(1, group["count"] + 1))
        value = json.loads(zlib.decompress(base64.b64decode(blob)))
        assert value["kind"] == kind
        name = f"deepseek-events/{kind}.json"
        if (HERE / name).exists():
            assert run.read(name) == value
        else:
            run.save(name, value)
        complete.add(kind)
    print(json.dumps({"page": page, "logs": len(rows), "events": sorted(complete)}), flush=True)
    if required <= complete:
        run.save("log-recovery/complete.json", {"job_id": job["id"], "pages": page+1,
                 "events": sorted(complete), "new_model_calls": 0})
        break
    if not rows:
        raise SystemExit("no_more_logs_before_complete_evidence")
    next_cursor = min(row["timestamp"] for row in rows)
    if next_cursor >= cursor:
        raise SystemExit("log_pagination_made_no_progress")
    cursor = next_cursor
else:
    raise SystemExit("bounded_log_pages_exhausted")

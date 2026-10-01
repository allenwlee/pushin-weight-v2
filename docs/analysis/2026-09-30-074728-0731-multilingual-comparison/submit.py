"""Lossless LZMA transport keeps the frozen job below OS argument-size limits.

The original zlib representation was 188,764 bytes before bootstrap code.
This changes transport encoding only, before any inference; packet and every
model request remain byte-identical after decompression. The transport itself
is hashed before the one allowed job submission. Do not use run.py submit.
"""
import base64
import hashlib
import json
import lzma
import shlex
import subprocess

import run


run.verify()
packet = run.encode(run.read("packet.json"))
compressed = lzma.compress(packet)
assert lzma.decompress(compressed) == packet
packed = base64.b64encode(compressed).decode()
program = "import base64,json,lzma;PACKET=json.loads(lzma.decompress(base64.b64decode(" + repr(packed) + ")));\n" + (run.HERE / "remote.py").read_text()
command = "python -c " + shlex.quote(program)
assert len(command.encode()) < 130000
run.save("transport-frozen.json", {"at": run.now(), "codec": "lzma",
    "transport_sha256": run.file_sha(run.HERE / "submit.py"),
    "frozen_manifest_sha256": run.file_sha(run.HERE / "frozen.json"),
    "packet_sha256": hashlib.sha256(packet).hexdigest(),
    "round_trip_verified": True, "start_command_bytes": len(command.encode()),
    "provider_calls": 0, "note": "Lossless transport compression only; frozen model inputs unchanged."})
run.save("render-preflight.json", run.preflight())
run.save("submission-started.json", {"at": run.now(), "service": run.SERVICE,
    "max_calls": 185, "transport": "submit.py", "program_sha256": hashlib.sha256(program.encode()).hexdigest()})
try:
    result = subprocess.run(["render", "jobs", "create", run.SERVICE, "--plan-id", "plan-crn-003",
        "--start-command", command, "--output", "json", "--confirm"],
        capture_output=True, text=True, timeout=45)
except subprocess.TimeoutExpired:
    run.save("submission-unknown.json", {"at": run.now(), "reason": "CLI timeout; inspect jobs; do not resubmit"})
    raise SystemExit("submission_uncertain_stop_no_resubmit") from None
if result.returncode:
    run.save("submission-failed.json", {"at": run.now(), "returncode": result.returncode, "stderr": result.stderr})
    raise SystemExit("submission_failed_no_resubmit")
job = json.loads(result.stdout)
run.save("job.json", job)
print(json.dumps({"job_id": job["id"], "status": job["status"], "max_calls": 185,
    "start_command_bytes": len(command.encode()), "lossless_input_parity": True}))

"""Stream the test harness to the actual worker; save private JSON locally."""

import argparse
import base64
import gzip
import json
import subprocess
from pathlib import Path

from database_scenario import CASES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--prepare-variant", action="store_true")
    parser.add_argument("--prepare-model-variant", action="store_true")
    parser.add_argument("--prepare-repair", action="store_true")
    parser.add_argument("--prepare-repair-model", action="store_true")
    parser.add_argument("--supplements", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("preserve first artifacts; output already exists")
    if any((args.execute, args.prepare_variant, args.prepare_model_variant,
            args.prepare_repair, args.prepare_repair_model)) and not args.fixture:
        raise ValueError("execution requires an inspected frozen fixture")
    if sum((args.execute, args.prepare_variant, args.prepare_model_variant,
            args.prepare_repair, args.prepare_repair_model)) > 1:
        raise ValueError("prepare a variant before execution")
    root = Path(__file__).parent
    script = "import os,sys,json,types,gzip,base64\nos.environ.setdefault('DJANGO_SETTINGS_MODULE','project.settings')\nimport django\ndjango.setup()\n"
    for name in ("production_replay", "database_scenario", "repair_scenario"):
        script += f"mod=types.ModuleType({name!r}); sys.modules[{name!r}]=mod\n"
        script += "exec(" + repr((root / (name + ".py")).read_text()) + ",mod.__dict__)\n"
    options = [args.case, args.expected_revision, args.run_id]
    script += "options=" + repr(options) + "\n"
    if args.fixture:
        fixture = json.loads(args.fixture.read_text())
        script += "fixture=json.loads(" + repr(json.dumps(fixture, ensure_ascii=False)) + ")\n"
    if args.execute:
        action = "mod.execute_repair(fixture,*options)" if fixture.get("repair_variant") else "sys.modules['database_scenario'].execute(fixture,*options)"
    elif args.prepare_variant:
        action = "sys.modules['database_scenario'].prepare_variant(fixture,*options[:2])"
    elif args.prepare_model_variant:
        action = "sys.modules['database_scenario'].prepare_model_variant(fixture,*options[:2])"
    elif args.prepare_repair:
        if not args.supplements:
            raise ValueError("repair preparation requires reviewed supplemental evidence")
        script += "supplements=json.loads(" + repr(args.supplements.read_text()) + ")\n"
        action = "mod.prepare_repair(fixture,supplements,*options[:2])"
    elif args.prepare_repair_model:
        action = "mod.prepare_repair_model(fixture,*options[:2])"
    else:
        action = "sys.modules['database_scenario'].prepare(*options[:2])"
    script += "try:\n    report=" + action + "\nexcept Exception as exc:\n"
    script += "    report={'status':'failed','error_type':type(exc).__name__}\n"
    script += "    if isinstance(exc,(ValueError,AssertionError)): report['reason']=str(exc)\n"
    script += "encoded=base64.b64encode(gzip.compress(json.dumps(report,ensure_ascii=False,default=str).encode())).decode()\n"
    script += "for offset in range(0,len(encoded),4000): print('PRODSIM_CHUNK:'+encoded[offset:offset+4000])\n"
    script += "sys.exit(0 if report['status'] in ('preflight_passed','scenario_passed') else 1)\n"
    remote = subprocess.run(
        ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20",
         "srv-d9ufj4e417fc73d93g20@ssh.oregon.render.com", "python -"],
        input=script, text=True, capture_output=True, timeout=240, check=False,
    )
    # Save only the structured report. SSH diagnostics never contain credentials.
    chunks = [line.removeprefix('PRODSIM_CHUNK:') for line in remote.stdout.splitlines()
              if line.startswith('PRODSIM_CHUNK:')]
    if not chunks:
        raise RuntimeError("worker returned no structured report")
    report = json.loads(gzip.decompress(base64.b64decode(''.join(chunks), validate=True)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "status": report["status"],
                      "request_hash": report.get("request_hash"),
                      "error_type": report.get("error_type"), "reason": report.get("reason")}))
    raise SystemExit(remote.returncode)


if __name__ == "__main__":
    main()

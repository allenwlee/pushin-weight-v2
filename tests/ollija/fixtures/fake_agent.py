#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def _increment(counter: Path) -> int:
    count = int(counter.read_text() or "0") if counter.exists() else 0
    counter.write_text(str(count + 1), encoding="utf-8")
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=(
            "success",
            "crash",
            "crash-once",
            "crash-once-edit",
            "edit-sleep",
            "sleep",
            "tree",
        ),
        required=True,
    )
    parser.add_argument("--counter", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pids", type=Path)
    args = parser.parse_args()

    if args.mode == "success":
        return 0
    if args.mode == "crash":
        return 7
    if args.mode == "crash-once":
        if args.counter is None:
            return 9
        return 7 if _increment(args.counter) == 0 else 0
    if args.mode == "crash-once-edit":
        if args.counter is None or args.output is None:
            return 9
        if _increment(args.counter) == 0:
            return 7
        args.output.write_text("completed by fake agent\n", encoding="utf-8")
        return 0
    if args.mode == "edit-sleep":
        if args.output is None:
            return 9
        args.output.write_text("incomplete work from fake agent\n", encoding="utf-8")
    if args.mode == "tree":
        if args.pids is None:
            return 9
        child = subprocess.Popen(
            [sys.executable, __file__, "--mode", "sleep"],
            start_new_session=False,
        )
        args.pids.write_text(f"{os.getpid()} {child.pid}\n", encoding="utf-8")
    while True:
        time.sleep(0.1)


if __name__ == "__main__":
    raise SystemExit(main())

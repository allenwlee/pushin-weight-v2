from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO

from .config import ConfigError, load_project_config
from .redaction import UnsafeOutputError, redact_text
from .results import CommandError, CommandResult
from .status import build_doctor_result, build_status_result, collect_status_facts

_COACHING = """common prompts:
  what's next?          ollija status
  check my setup        ollija doctor
  start work            ollija start
  show local preview    ollija preview
  stage this            ollija stage
  record phone approval ollija approve iphone
  release next beta     ollija release
  verify production     ollija verify-production
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ollija",
        description="PushinWeight staging and release coach.",
        epilog=_COACHING,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("status", "Read live authorities and recommend exactly one next action."),
        ("doctor", "Check the authoritative host, tools, auth, Git, and databases."),
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        subparser.add_argument(
            "--json",
            action="store_true",
            dest="json_output",
            help="Emit the versioned structured result envelope.",
        )
    return parser


def render_human(result: CommandResult) -> str:
    lines = [
        f"ollija {redact_text(result.command)}: {redact_text(result.status)}",
        redact_text(result.summary),
        f"State: {redact_text(result.state)}",
    ]
    for warning in result.warnings:
        lines.append(f"Warning: {redact_text(warning)}")
    for error in result.errors:
        lines.append(f"Error [{error.code}]: {redact_text(error.message)}")
    if result.next_action:
        lines.append(
            "Next: "
            f"{redact_text(result.next_action.command)} — "
            f"{redact_text(result.next_action.reason)}"
        )
    return "\n".join(lines)


def emit_result(
    result: CommandResult,
    *,
    json_output: bool,
    stream: TextIO,
) -> None:
    if json_output:
        stream.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")
    else:
        stream.write(render_human(result) + "\n")


def _config_failure(command: str, exc: Exception) -> CommandResult:
    return CommandResult(
        command=command,
        status="failed",
        state="blocked",
        summary="ollija could not load the project contract.",
        errors=(
            CommandError(
                code="project_contract_invalid",
                message=redact_text(str(exc)),
            ),
        ),
    )


def main(
    argv: list[str] | None = None,
    *,
    cwd: Path | None = None,
    stream: TextIO | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output = stream or sys.stdout
    working_directory = (cwd or Path.cwd()).resolve()
    try:
        config = load_project_config(working_directory)
        facts = collect_status_facts(config, cwd=working_directory)
        result = (
            build_status_result(facts)
            if args.command == "status"
            else build_doctor_result(facts)
        )
        emit_result(result, json_output=args.json_output, stream=output)
    except (ConfigError, UnsafeOutputError) as exc:
        result = _config_failure(args.command, exc)
        emit_result(result, json_output=args.json_output, stream=output)

    return {"ok": 0, "blocked": 2, "failed": 1}[result.status]

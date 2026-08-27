from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, TextIO

from .policy import (
    DatabaseInspection,
    PolicyError,
    authorize,
    guard_environment,
    load_policy,
)


class Runtime(Protocol):
    def inspect_source(self, url: str) -> DatabaseInspection: ...

    def inspect_target(self, url: str) -> DatabaseInspection: ...

    def execute(self, action: str, *, recovery: str | None = None) -> dict[str, object]: ...


def _default_policy_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "staging_refresh.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="refresh-staging-data")
    parser.add_argument("--policy", type=Path, default=_default_policy_path())
    subcommands = parser.add_subparsers(dest="action", required=True)
    subcommands.add_parser("preflight", help="prove source and target safety without mutation")
    refresh = subcommands.add_parser("refresh", help="build, verify, and activate a shadow copy")
    refresh.add_argument("--confirm", required=True)
    subcommands.add_parser("verify", help="verify the active staging database and receipt")
    for action in ("rollback", "prune"):
        command = subcommands.add_parser(action)
        command.add_argument("--recovery", required=True)
        command.add_argument("--confirm", required=True)
    return parser


def _emit(stream: TextIO, payload: Mapping[str, object]) -> None:
    stream.write(json.dumps(dict(payload), sort_keys=True, separators=(",", ":")) + "\n")


def run(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    runtime: Runtime | None = None,
    stdout: TextIO | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    values = dict(os.environ if environ is None else environ)
    output = stdout or sys.stdout
    try:
        policy = load_policy(args.policy)
        confirmation = getattr(args, "confirm", None)
        recovery = getattr(args, "recovery", None)
        environment_guard = guard_environment(
            policy,
            action=args.action,
            environ=values,
            confirmation=confirmation,
            recovery=recovery,
        )
        if runtime is None:
            from .database import PostgresRuntime

            runtime = PostgresRuntime(
                policy,
                source_url=values.get(policy.source.environment),
                target_url=values.get(policy.target.environment),
            )

        source = None
        if environment_guard.source is not None:
            source = runtime.inspect_source(values[policy.source.environment])
        target = runtime.inspect_target(values[policy.target.environment])
        authorization = authorize(
            policy,
            action=args.action,
            environ=values,
            source=source,
            target=target,
            confirmation=confirmation,
            recovery=recovery,
        )
        if args.action in {"preflight", "verify"}:
            _emit(
                output,
                {
                    "action": args.action,
                    "source_database": (
                        authorization.source.database if authorization.source else None
                    ),
                    "status": "authorized",
                    "target_database": authorization.target.database,
                },
            )
            return 0

        result = runtime.execute(args.action, recovery=authorization.recovery)
        _emit(output, {"status": "complete", **result})
        return 0
    except PolicyError as exc:
        _emit(output, {"status": "rejected", "code": str(exc)})
        return 2
    except Exception:  # noqa: BLE001 - arbitrary failures must cross a secret-free boundary
        _emit(output, {"status": "error", "code": "runtime_error"})
        return 1


def main() -> int:
    return run()

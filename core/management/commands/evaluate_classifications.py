"""Score frozen Stage 1 candidate output against adjudicated heldout gold."""

from __future__ import annotations

import json
from pathlib import Path
from types import MethodType

from django.core.management.base import BaseCommand

from core.classification_evaluation import (
    EvaluationInputError,
    evaluate_classification_files,
    safe_error_document,
)


class Command(BaseCommand):
    help = "Evaluate file-based Stage 1 classifications without DB or providers."

    def create_parser(self, prog_name, subcommand, **kwargs):
        parser = super().create_parser(prog_name, subcommand, **kwargs)

        def structured_error(parser_self, _message):
            error = EvaluationInputError(
                "invalid_arguments", "invalid classification evaluation arguments"
            )
            parser_self.exit(
                2, json.dumps(safe_error_document(error), sort_keys=True) + "\n"
            )

        parser.error = MethodType(structured_error, parser)
        return parser

    def add_arguments(self, parser) -> None:
        parser.add_argument("--candidate", required=True, type=Path)
        parser.add_argument("--gold", required=True, type=Path)
        parser.add_argument("--policy", type=Path)
        parser.add_argument("--output", type=Path)

    def handle(self, *args, **options) -> None:
        try:
            policy = self._read_policy(options.get("policy"))
            result = evaluate_classification_files(
                options["candidate"], options["gold"], policy=policy
            )
            serialized = json.dumps(
                result, ensure_ascii=False, indent=2, sort_keys=True
            )
            output_path = options.get("output")
            if output_path is None:
                self.stdout.write(serialized)
                return
            self._write_result(output_path, serialized)
            self.stdout.write(
                json.dumps(
                    {
                        "assessment": result["assessment"]["status"],
                        "evaluation_identity": result["identity"][
                            "evaluation_identity"
                        ],
                        "output": str(output_path),
                        "status": result["status"],
                    },
                    sort_keys=True,
                )
            )
        except EvaluationInputError as exc:
            self.stderr.write(json.dumps(safe_error_document(exc), sort_keys=True))
            raise SystemExit(2) from exc

    @staticmethod
    def _read_policy(path: Path | None):
        if path is None:
            return None
        try:
            policy = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise EvaluationInputError(
                "policy_unreadable", f"could not read evaluation policy: {path}"
            ) from exc
        return policy

    @staticmethod
    def _write_result(path: Path, serialized: str) -> None:
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(serialized + "\n", encoding="utf-8")
            temporary.replace(path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise EvaluationInputError(
                "result_unwritable", f"could not write evaluation result: {path}"
            ) from exc

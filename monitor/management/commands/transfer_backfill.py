"""Export admitted staging members or apply one bounded, frozen transfer."""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from monitor.backfill_promotion import (
    MAX_BYTES,
    encoded,
    export_posts,
    inspect_source,
    promote_posts,
    reconcile_quotes,
    reconcile_saved_quotes,
)


class Command(BaseCommand):
    help = "Transfer collected backfill Posts without provider calls; promotion defaults to read-only."

    def add_arguments(self, parser):
        actions = parser.add_subparsers(dest="action", required=True)
        export = actions.add_parser("export")
        export.add_argument("--job", required=True)
        export.add_argument("--output", type=Path, required=True)
        export.add_argument("--after", default="")
        export.add_argument("--limit", type=int, default=100)
        inspect = actions.add_parser("inspect-source")
        inspect.add_argument("--job", required=True)
        inspect.add_argument("--after", default="")
        for name in ("promote", "reconcile-quotes", "reconcile-saved", "pull"):
            child = actions.add_parser(name)
            if name in {"promote", "reconcile-quotes"}:
                child.add_argument("--package", type=Path, required=True)
            else:
                child.add_argument("--job", required=True)
            for field in ("host", "name", "user"):
                child.add_argument("--target-" + field, required=True)
                if name == "pull":
                    child.add_argument("--source-" + field, required=True)
            if name == "pull":
                child.add_argument("--deadline", type=datetime.fromisoformat, required=True)
                child.add_argument("--limit", type=int, default=100)
                child.add_argument("--max-packages", type=int, default=1000)
            child.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        try:
            if options["action"] == "inspect-source":
                result = inspect_source(options["job"], after=options["after"])
            elif options["action"] == "export":
                package = export_posts(options["job"], after=options["after"], limit=options["limit"])
                if package is None:
                    result = {"exhausted": True, "posts": 0}
                else:
                    output = options["output"]
                    body = encoded(package)
                    if output.exists():
                        if output.read_bytes() != body:
                            raise ValueError("output already contains a different export")
                    else:
                        output.parent.mkdir(parents=True, exist_ok=True)
                        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as temporary:
                            temp_path = Path(temporary.name)
                            temporary.write(body)
                            temporary.flush()
                            os.fsync(temporary.fileno())
                        try:
                            # Exclusive link prevents a concurrent export from
                            # overwriting an operator's frozen package.
                            os.link(temp_path, output)
                        finally:
                            temp_path.unlink(missing_ok=True)
                    result = {"posts": len(package["ids"]), "next_after": package["next_after"],
                              "sha256": package["sha256"], "output": str(output)}
            elif options["action"] in {"pull", "reconcile-saved"}:
                target = {k: options["target_" + k] for k in ("host", "name", "user")}
                if options["action"] == "pull":
                    from monitor.backfill_transfer import pull_job
                    result = pull_job(options["job"], target=target,
                        source={k: options["source_" + k] for k in ("host", "name", "user")},
                        deadline=options["deadline"], limit=options["limit"],
                        max_packages=options["max_packages"], execute=options["execute"],
                        emit=lambda value: self.stderr.write("TRANSFER_PROGRESS " + json.dumps(value)))
                else:
                    result = reconcile_saved_quotes(options["job"], target=target, execute=options["execute"])
            else:
                with options["package"].open("rb") as source:
                    body = source.read(MAX_BYTES + 101)
                if len(body) > MAX_BYTES + 100:
                    raise ValueError("export too large")
                package = json.loads(body)
                target = {k: options["target_" + k] for k in ("host", "name", "user")}
                operation = promote_posts if options["action"] == "promote" else reconcile_quotes
                result = operation(package, target=target, execute=options["execute"])
        except (ValueError, TypeError, KeyError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, sort_keys=True))

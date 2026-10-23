"""Export admitted staging members or apply one bounded, frozen transfer."""
import json
import os
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from monitor.backfill_promotion import (
    MAX_BYTES,
    encoded,
    export_posts,
    promote_posts,
    reconcile_quotes,
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
        for name in ("promote", "reconcile-quotes"):
            child = actions.add_parser(name)
            child.add_argument("--package", type=Path, required=True)
            for field in ("host", "name", "user"):
                child.add_argument("--target-" + field, required=True)
            child.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        try:
            if options["action"] == "export":
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

"""Preview/copy/verify staff files against the configured staff_media backend."""

import json

from django.core.management.base import BaseCommand, CommandError

from core.staff_assets.transfer import transfer_staff_media


class Command(BaseCommand):
    help = "Copy staff files to configured storage with SHA-256 checks; preview by default."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-root", help="Existing local staff-media directory"
        )
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument(
            "--apply", action="store_true", help="Copy missing files only"
        )
        mode.add_argument(
            "--verify-only", action="store_true", help="Verify destination bytes"
        )

    def handle(self, *args, **options):
        try:
            report = transfer_staff_media(
                source_root=options["source_root"],
                apply=options["apply"],
                verify_only=options["verify_only"],
            )
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report, sort_keys=True))
        if report["errors"]:
            raise CommandError(
                "Staff media transfer verification failed; see JSON errors"
            )

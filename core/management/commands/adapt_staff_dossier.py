import json
from pathlib import Path

from django.core.management.base import BaseCommand

from core.staff_assets.manifest import from_deepseek_dossier


class Command(BaseCommand):
    help = "Convert the saved DeepSeek prototype to a generic manifest; no DB writes."

    def add_arguments(self, parser):
        parser.add_argument("dossier")
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        manifest = from_deepseek_dossier(
            json.loads(Path(options["dossier"]).read_text())
        )
        Path(options["output"]).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        )
        self.stdout.write(f"Wrote {len(manifest['people'])} staff observations")

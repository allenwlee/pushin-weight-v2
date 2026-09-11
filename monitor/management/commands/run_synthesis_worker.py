from __future__ import annotations

import json
import os
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from monitor.post_synthesis import process_synthesis_batch
from scripts.database_lock import (
    DatabaseLockError,
    acquire_synthesis_coordination_lock,
)
from x_monitor.config import load_config
from x_monitor.translator import AnthropicClaudeClient


class Command(BaseCommand):
    help = "Poll PostgreSQL for durable rich-synthesis demand."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options) -> None:
        config = load_config(Path("config.yaml")).synthesis
        if not config.provider_calls_active:
            if options["once"]:
                raise CommandError("synthesis provider calls are disabled")
            self.stdout.write("synthesis provider calls are disabled; worker is idle")
            while True:
                time.sleep(60)
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise CommandError("DEEPSEEK_API_KEY is required")
        database_url = os.environ.get("DATABASE_URL")
        environment = os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT")
        if not database_url or environment not in {"staging", "production"}:
            raise CommandError("synthesis worker database/environment is invalid")
        client = AnthropicClaudeClient(api_key=api_key, base_url=config.base_url)
        try:
            with acquire_synthesis_coordination_lock(
                database_url, environment=environment
            ):
                while True:
                    result = process_synthesis_batch(config=config, client=client)
                    if options["as_json"]:
                        self.stdout.write(json.dumps(result, sort_keys=True))
                    elif result["claimed"]:
                        self.stdout.write(
                            "synthesis "
                            f"claimed={result['claimed']} succeeded={result['succeeded']} "
                            f"failed={result['failed']}"
                        )
                    if options["once"]:
                        return
                    time.sleep(config.poll_seconds)
        except DatabaseLockError as exc:
            raise CommandError(str(exc)) from exc

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.models import Post
from monitor.post_artifacts import read_post_content_many
from monitor.post_synthesis import request_post_synthesis
from x_monitor.config import load_config


class Command(BaseCommand):
    help = "Request or poll shared rich-synthesis work for stored posts."

    def add_arguments(self, parser) -> None:
        parser.add_argument("post_ids", nargs="+")
        parser.add_argument(
            "--reason",
            choices=("visible", "expanded", "lookahead", "prewarm", "operator"),
            default="operator",
        )
        parser.add_argument("--poll-only", action="store_true")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options) -> None:
        config = load_config(Path("config.yaml")).synthesis
        post_ids = list(dict.fromkeys(str(value) for value in options["post_ids"]))
        if len(post_ids) > config.demand_batch_limit:
            raise CommandError("post_ids limit exceeded")

        posts = list(Post.objects.filter(pk__in=post_ids))
        posts_by_id = {str(post.pk): post for post in posts}
        missing = [post_id for post_id in post_ids if post_id not in posts_by_id]
        if missing:
            raise CommandError(f"unknown post IDs: {', '.join(missing)}")

        if not options["poll_only"]:
            request_post_synthesis(
                post_ids=post_ids,
                reason=options["reason"],
                config=config,
            )

        projections = read_post_content_many(posts)
        payload = {
            "results": [
                {
                    "post_id": post_id,
                    "status": projections[post_id].synthesis_status,
                    "synthesis": dict(projections[post_id].synthesis),
                    "literal": dict(projections[post_id].literal),
                }
                for post_id in post_ids
            ]
        }
        if options["as_json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True))
            return
        for result in payload["results"]:
            self.stdout.write(f"{result['post_id']} {result['status']}")

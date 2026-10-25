"""Move completed staging members through the existing bounded promotion path.

The destination process keeps its own connection. A short-lived child reads
staging using a separately named secret; credentials never enter arguments or
receipts. Resume evidence is the destination's existing collection membership.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.utils import timezone

from core.measurement_taxonomy import require
from core.models import CollectionJob, CollectionObservation
from monitor.backfill_promotion import (
    MAX_BYTES,
    database_identity,
    membership,
    promote_posts,
    reconcile_saved_quotes,
    schema_signature,
    validate_package,
)
from monitor.run_lock import harvest_writer_lock

SOURCE_ENV = "BACKFILL_STAGING_DATABASE_URL"


class SourceReader:
    def __init__(self, job_id, *, source, deadline):
        self.job_id, self.source, self.deadline = str(job_id), source, deadline
        value = os.environ.get(SOURCE_ENV, "")
        require(bool(value), "staging transfer credential missing")
        parsed = urlsplit(value)
        require(parsed.scheme in {"postgres", "postgresql"} and {
            "host": parsed.hostname, "name": unquote(parsed.path.lstrip("/")),
            "user": unquote(parsed.username or ""),
        } == source, "staging transfer credential identity mismatch")
        self.environment = {**os.environ, "DATABASE_URL": value,
                            "X_MONITOR_DEPLOYMENT_ENVIRONMENT": "staging"}

    def _invoke(self, action, *arguments):
        seconds = (self.deadline - timezone.now()).total_seconds()
        require(seconds > 0, "transfer deadline exhausted")
        try:
            result = subprocess.run([sys.executable, "manage.py", "transfer_backfill", action,
                "--job", self.job_id, *arguments], env=self.environment,
                capture_output=True, text=True, timeout=min(60, seconds), check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("staging transfer read failed; no destination write") from None
        # Provider/connection errors can include credentials. Never echo child
        # output in a failed read's operator-visible exception.
        require(result.returncode == 0, "staging transfer read failed; no destination write")
        try:
            return json.loads(result.stdout)
        except (ValueError, TypeError):
            raise ValueError("invalid staging transfer metadata") from None

    def info(self, after):
        return self._invoke("inspect-source", "--after", after)

    def package(self, after, limit):
        with tempfile.TemporaryDirectory(prefix="backfill-transfer-") as directory:
            path = Path(directory) / "posts.json"
            meta = self._invoke("export", "--after", after, "--limit", str(limit), "--output", str(path))
            if meta.get("exhausted"):
                return None
            require(path.is_file() and path.stat().st_size <= MAX_BYTES + 100, "transfer package size invalid")
            package = json.loads(path.read_bytes())
            require(package.get("sha256") == meta.get("sha256"), "transfer transport hash mismatch")
            return package


def pull_job(job_id, *, source, target, deadline, execute=False, limit=100,
             max_packages=1000, reader=None, emit=None):
    """Read-only by default; verify the saved prefix before resuming any write."""
    require(database_identity() == target, "promotion target database mismatch")
    require(set(source) == {"host", "name", "user"}
            and all(isinstance(v, str) and v for v in source.values()), "invalid transfer source identity")
    require((source["host"], source["name"]) != (target["host"], target["name"]), "source and target database must differ")
    require(timezone.is_aware(deadline) and deadline > timezone.now(), "transfer deadline exhausted")
    require(type(limit) is int and 1 <= limit <= 100, "export limit must be 1–100")
    require(type(max_packages) is int and 1 <= max_packages <= 10000, "invalid transfer package allowance")
    reader = reader or SourceReader(job_id, source=source, deadline=deadline)
    emit = emit or (lambda value: None)
    jobs = CollectionJob.objects.filter(source_id="x", operation="x_backfill", state="completed",
        definition__scope__adapter="x-staging-promotion/v1",
        definition__scope__source__job_id=str(job_id))
    observations = CollectionObservation.objects.filter(run__job__in=jobs, source_subject_kind="post")

    def inspect():
        after = observations.exclude(post_id=None).order_by("-post_id").values_list("post_id", flat=True).first() or ""
        info = reader.info(after)
        require(info["schema"] == schema_signature() and info["source"]["database"] == source
                and info["source"]["job_id"] == str(job_id), "transfer source changed")
        require(not jobs.exclude(definition__scope__source=info["source"]).exists(), "saved transfer source changed")
        require(membership(observations) == info["prefix"], "saved transfer has missing or unexpected prefix members")
        return after, info

    if not execute:
        after, info = inspect()
        return {"status": "inspection", "source": info["source"], "source_posts": info["members"]["count"],
                "saved_posts": info["prefix"]["count"], "after": after, "provider_calls": 0}

    def apply(operation, *args):
        while timezone.now() < deadline:
            try:
                return operation(*args, target=target, execute=True)
            except ValueError as exc:
                if str(exc) not in {"promotion waiting for live writer", "promotion yielding to live writer"}:
                    raise
                emit({"status": "waiting_for_live_writer"})
                time.sleep(min(10, max(0, (deadline - timezone.now()).total_seconds())))
        raise ValueError("transfer deadline exhausted")

    # This coordination key is distinct from the live writer key. Holding it
    # cannot reserve the harvester's writer while source reads or waits occur.
    with harvest_writer_lock(execution_mode="backfill", entrypoint="management.backfill.transfer",
                             lock_scope="staging-transfer:" + str(job_id)) as lease:
        require(lease.acquired, "staging transfer already running")
        after, info = inspect()
        packages, new_posts = 0, 0
        for _ in range(max_packages):
            require(timezone.now() < deadline, "transfer deadline exhausted")
            package = reader.package(after, limit)
            if package is None:
                break
            validate_package(package)
            require(package["source"] == info["source"] and package["after"] == after,
                    "transfer package source or cursor changed")
            result = apply(promote_posts, package)
            packages += 1
            new_posts += len(result["new_post_ids"])
            after = package["next_after"]
            emit({"status": "promoted", "job_id": result["job_id"], "posts": result["posts"],
                  "new_posts": len(result["new_post_ids"]), "after": after})
        saved = membership(observations)
        complete = saved == info["members"]
        quotes = [apply(reconcile_saved_quotes, job.pk) for job in jobs.iterator(chunk_size=100)] if complete else []
        return {"status": "completed" if complete else "partial", "source_job_id": str(job_id),
                "source_posts": info["members"]["count"], "saved_posts": saved["count"],
                "new_posts": new_posts, "packages": packages, "after": after,
                "pending_quotes": sum(len(q["pending"]) for q in quotes),
                "changed_quotes": sum(len(q["changed"]) for q in quotes), "provider_calls": 0}

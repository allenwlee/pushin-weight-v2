"""Resumable bounded transport, with real destination transactions and child reads."""
import copy
import hashlib
import json
import os
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.models import CollectionObservation, Post
from monitor import backfill_promotion as promotion
from monitor import backfill_transfer as transfer
from tests.test_backfill_collection import live_writer  # noqa: F401
from tests.test_backfill_prefetch import http_pages, pipeline  # noqa: F401
from tests.test_backfill_promotion import (  # noqa: F401
    destination_package,
    exported,
    seal,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def members(ids):
    return {"count": len(ids), "sha256": hashlib.sha256(b"".join(promotion.encoded(i) + b"\n" for i in sorted(ids))).hexdigest()}


class Reader:
    def __init__(self, package):
        self.value, self.calls = package, []

    def info(self, after):
        return {"source": self.value["source"], "schema": self.value["schema"],
                "members": members(self.value["ids"]), "prefix": members([i for i in self.value["ids"] if i <= after])}

    def package(self, after, limit):
        self.calls.append(after)
        ids = [i for i in self.value["ids"] if i > after][:limit]
        if not ids:
            return None
        p = copy.deepcopy(self.value)
        p.update(ids=ids, after=after, next_after=ids[-1])
        authors = {r["author_id"] for r in p["rows"]["Post"] if r["tweet_id"] in ids}
        for model, rows in p["rows"].items():
            key, allowed = ("post_id", ids)
            if model == "Post":
                key = "tweet_id"
            elif model == "Account":
                key, allowed = "account_key", authors
            elif model in {"XAccountDetail", "AccountProfileSnapshot"}:
                key, allowed = "account_id", authors
            p["rows"][model] = [r for r in rows if r[key] in allowed]
        return seal(p)


def kwargs(reader):
    return {"source": reader.value["source"]["database"], "target": promotion.database_identity(),
            "deadline": timezone.now() + timedelta(minutes=5), "reader": reader, "limit": 1}


def test_pull_command_defaults_to_read_only(exported, monkeypatch):  # noqa: F811
    reader = Reader(destination_package(exported))
    monkeypatch.setattr(transfer, "SourceReader", lambda *a, **k: reader)
    options = kwargs(reader)
    stdout = StringIO()
    call_command("transfer_backfill", "pull", job=reader.value["source"]["job_id"],
        **{"source_" + k: v for k, v in options["source"].items()},
        **{"target_" + k: v for k, v in options["target"].items()},
        deadline=options["deadline"], stdout=stdout)
    assert json.loads(stdout.getvalue())["status"] == "inspection"
    assert not reader.calls
    assert not Post.objects.filter(pk__in=reader.value["ids"]).exists()


def test_bounded_pull_resumes_and_repairs_quotes_after_package_is_gone(exported):  # noqa: F811
    package = destination_package(exported)
    child, parent = package["ids"]
    next(r for r in package["rows"]["Post"] if r["tweet_id"] == child)["quoted_status_id_id"] = parent
    reader = Reader(seal(package))
    first = transfer.pull_job(package["source"]["job_id"], **kwargs(reader), execute=True, max_packages=1)
    assert first["status"] == "partial" and first["new_posts"] == first["saved_posts"] == 1
    assert Post.objects.get(pk=child).quoted_status_id_id is None
    reader.calls.clear()
    second = transfer.pull_job(package["source"]["job_id"], **kwargs(reader), execute=True)
    assert second["status"] == "completed" and second["new_posts"] == 1 and second["saved_posts"] == 2
    assert reader.calls[0] == child
    assert Post.objects.get(pk=child).quoted_status_id_id == parent
    third = transfer.pull_job(package["source"]["job_id"], **kwargs(reader), execute=True)
    assert third["status"] == "completed" and third["new_posts"] == third["packages"] == 0


def test_interruption_after_commit_resumes_from_durable_membership(exported, monkeypatch):  # noqa: F811
    reader = Reader(destination_package(exported))
    original = transfer.promote_posts
    def lost_receipt(*a, **k):
        original(*a, **k)
        raise RuntimeError("fixture receipt lost after commit")
    monkeypatch.setattr(transfer, "promote_posts", lost_receipt)
    with pytest.raises(RuntimeError, match="receipt lost"):
        transfer.pull_job(reader.value["source"]["job_id"], **kwargs(reader), execute=True)
    monkeypatch.setattr(transfer, "promote_posts", original)
    reader.calls.clear()
    result = transfer.pull_job(reader.value["source"]["job_id"], **kwargs(reader), execute=True)
    assert result["status"] == "completed" and result["new_posts"] == 1
    assert reader.calls[0] == reader.value["ids"][0]


def test_source_read_leaves_live_writer_available(exported, live_writer):  # noqa: F811
    reader = Reader(destination_package(exported))
    original = reader.package
    checks = []
    def read(after, limit):
        with live_writer():
            checks.append(after)
            return original(after, limit)
    reader.package = read
    result = transfer.pull_job(reader.value["source"]["job_id"], **kwargs(reader), execute=True)
    assert result["status"] == "completed" and len(checks) == 3


def test_missing_saved_prefix_refuses_to_skip_posts(exported):  # noqa: F811
    reader = Reader(destination_package(exported))
    transfer.pull_job(reader.value["source"]["job_id"], **kwargs(reader), execute=True)
    CollectionObservation.objects.filter(post_id=reader.value["ids"][0]).delete()
    reader.calls.clear()
    with pytest.raises(ValueError, match="prefix members"):
        transfer.pull_job(reader.value["source"]["job_id"], **kwargs(reader), execute=True)
    assert not reader.calls


@pytest.mark.parametrize("fault", ["target", "source", "deadline", "package"])
def test_wrong_identity_deadline_or_package_stops_before_writes(exported, fault):  # noqa: F811
    reader = Reader(destination_package(exported))
    options = kwargs(reader)
    if fault == "target":
        options["target"] = {**options["target"], "name": "wrong"}
    elif fault == "source":
        options["source"] = {**options["source"], "name": "wrong"}
    elif fault == "deadline":
        options["deadline"] = timezone.now() - timedelta(seconds=1)
    else:
        original = reader.package
        reader.package = lambda after, limit: {**original(after, limit), "after": "wrong"}
    with pytest.raises(ValueError):
        transfer.pull_job(reader.value["source"]["job_id"], **options, execute=True)
    assert not Post.objects.filter(pk__in=reader.value["ids"]).exists()


def test_real_child_reads_exact_source_without_mutating_it(exported, monkeypatch):  # noqa: F811
    monkeypatch.setenv(transfer.SOURCE_ENV, os.environ["DATABASE_URL"])
    reader = transfer.SourceReader(exported["source"]["job_id"], source=promotion.database_identity(),
        deadline=timezone.now() + timedelta(minutes=2))
    before = list(Post.objects.order_by("pk").values())
    info = reader.info("")
    package = reader.package("", 1)
    assert info["members"] == members(exported["ids"])
    assert package["ids"] == exported["ids"][:1]
    assert list(Post.objects.order_by("pk").values()) == before


def test_source_credential_does_not_fall_back_or_enter_arguments(monkeypatch):
    source = {"host": "source-host", "name": "source-db", "user": "source-user"}
    monkeypatch.delenv(transfer.SOURCE_ENV, raising=False)
    with pytest.raises(ValueError, match="credential missing"):
        transfer.SourceReader("job", source=source, deadline=timezone.now() + timedelta(minutes=1))
    monkeypatch.setenv(transfer.SOURCE_ENV, "postgresql://source-user:dummy@source-host/source-db")
    reader = transfer.SourceReader("job", source=source, deadline=timezone.now() + timedelta(minutes=1))
    def failed(args, **kwargs):
        assert "dummy" not in repr(args)
        assert "dummy" in kwargs["env"]["DATABASE_URL"]
        return type("Result", (), {"returncode": 1, "stdout": "dummy", "stderr": "dummy"})()
    monkeypatch.setattr(transfer.subprocess, "run", failed)
    with pytest.raises(ValueError) as exc:
        reader.info("")
    assert "dummy" not in str(exc.value)

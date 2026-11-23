"""Foreground portrait bytes and the writer request under worker/storage failures."""

import base64
import os
import time

import billiard
import pytest
from django.core.files.storage import storages
from django.utils import timezone

from core.models import StaffCollectionWork
from core.staff_assets import graphics_references
from monitor.editorial import graphics_cast, graphics_pipeline
from monitor.editorial.chatter_trends import DECISION_SCOPE, ROLLING_LANE
from monitor.editorial.graphics_contracts import WRITER_LED
from monitor.editorial.graphics_packages import materialize_package
from tests.editorial_support import editorial_storage, person_photo  # noqa: F401
from tests.test_chatter_graphics_publication import media_transport, personalized
from tests.test_graphics_chatter_adapter import (  # noqa: F401
    copy_result,
    frozen_chatter,
    prepared,
)

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]
named_passage = pytest.mark.parametrize("frozen_chatter", ["Source Maker announced a preview."], indirect=True)


@pytest.fixture
def writer_portrait(frozen_chatter, editorial_storage, monkeypatch):  # noqa: F811
    row, _, _ = frozen_chatter
    personalized(row)
    person, _, photo = person_photo("Source Maker")
    row.selection.update(subject="Source Maker announces a preview", person_ids=[str(person.pk)], source_identities=[{
        "post_id": "98001", "person_links": [{"person_id": str(person.pk), "role": "mentioned",
                                              "resolution_status": "confirmed"}],
    }])
    row.save(update_fields=["selection"])
    row.run.scope_key = DECISION_SCOPE
    row.run.config_snapshot["editorial"]["chatter"]["discovery_lane"] = ROLLING_LANE
    row.run.save(update_fields=["scope_key", "config_snapshot"])
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    request = prepared(row)
    run, _ = materialize_package(request)
    proposal = copy_result(used=["F01"])
    proposal.update(schema_version=WRITER_LED, candidates=[{
        **proposal["candidates"][0], "still_pitch": "An illustrated counter.",
        "motion_prompt": "The camera pans.",
    }])
    fake, _ = media_transport(proposal)
    sent = []

    def transport(endpoint, key, body, **kwargs):
        sent.append(body)
        return fake(endpoint, key, body, **kwargs)

    def advance():
        keys = {request["writer_route"]["key_env"]: "fixture"}
        result = graphics_pipeline.advance_step(run.pk, keys=keys, transport=transport)
        run.refresh_from_db()
        return result

    return run, photo, sent, advance


@named_passage
@pytest.mark.parametrize("stall", [False, True])
def test_c1_uses_one_verified_read_or_publishes_when_the_read_stalls(writer_portrait, monkeypatch, stall):
    run, photo, sent, advance = writer_portrait
    stored = storages["staff_media"].path(photo.media.storage_name)
    with open(stored, "rb") as source:
        expected = base64.b64encode(source.read()).decode()
    # A FIFO without a writer blocks even before the first byte. Only cancelling
    # the actual I/O keeps this test within its foreground budget.
    if stall:
        os.unlink(stored)
        os.mkfifo(stored)
    monkeypatch.setattr(graphics_cast, "PORTRAIT_WAIT_SECONDS", 2)
    children = []
    popen = graphics_references.subprocess.Popen

    def record_process(args, *positional, **kwargs):
        child = popen(args, *positional, **kwargs)
        if args[-1] == graphics_references._READ_OBJECT:
            children.append(child)
        return child

    monkeypatch.setattr(graphics_references.subprocess, "Popen", record_process)
    started = time.monotonic()
    result = advance()
    elapsed = time.monotonic() - started
    assert result["state"] == "completed" and result["stage"] == "C1"
    assert len(sent) == 1 and len(children) == 1 and children[0].poll() is not None, run.decisions.get('writer_person_intake')
    assert elapsed < 5
    manifest = run.decisions["writer_cast"]
    assert [ref["sha256"] for ref in manifest["assets"]] == ([] if stall else [photo.media_id])
    if stall:
        assert any("deadline elapsed" in reason for reason in manifest["gaps"])
        assert "data:image" not in str(sent[0])
    else:
        assert expected in str(sent[0])
        call = run.provider_calls.get(stage__endswith=":C1")
        assert call.request_packet["assets"][0]["sha256"] == photo.media_id


@named_passage
def test_restart_during_first_scan_keeps_original_deadline(writer_portrait, monkeypatch):
    from datetime import timedelta

    run, _, sent, advance = writer_portrait
    with monkeypatch.context() as patch:
        def interrupted(*args, **kwargs):
            raise RuntimeError("worker exited")
        patch.setattr(graphics_pipeline, "prepare_person_cast", interrupted)
        with pytest.raises(RuntimeError, match="worker exited"):
            advance()
    run.refresh_from_db()
    start = run.decisions["writer_person_intake"]["started_at"]
    assert "writer_cast" not in run.decisions
    after = timezone.now() + timedelta(seconds=21)
    monkeypatch.setattr(timezone, "now", lambda: after)
    def unexpected_process(*args, **kwargs):
        pytest.fail("An expired scan started another storage reader")
    monkeypatch.setattr(graphics_references.subprocess, "run", unexpected_process)
    result = advance()
    assert result["state"] == "completed" and len(sent) == 1
    assert run.decisions["writer_person_intake"]["started_at"] == start
    assert run.decisions["writer_cast"]["assets"] == []
    assert any("deadline elapsed" in gap for gap in run.decisions["writer_cast"]["gaps"])


@named_passage
def test_verified_subject_remains_in_c1_while_another_reaches_the_deadline(writer_portrait, monkeypatch):
    from core.staff_assets.person_research import POLICY

    run, photo, sent, advance = writer_portrait
    ref = graphics_cast.portrait_asset(photo.person_id, "Source Maker", ["F01"])
    other, _, _ = person_photo("Second Person", photo=False)
    pending = StaffCollectionWork.objects.create(person=other, fingerprint="pending-fixture", policy_version=POLICY)
    run.decisions = {**run.decisions, "writer_person_intake": {
        "started_at": timezone.now().isoformat(), "gaps": [], "subjects": [
            {"person_id": str(photo.person_id), "name": "Source Maker", "asset": ref,
             "work_id": None, "fact_ids": ["F01"]},
            {"person_id": str(other.pk), "name": "Second Person", "asset": None,
             "work_id": pending.pk, "fact_ids": ["F02"]},
        ],
    }}
    run.save(update_fields=["decisions"])
    monkeypatch.setattr(graphics_cast, "PORTRAIT_WAIT_SECONDS", 2)
    result = advance()
    assert result["state"] == "completed" and len(sent) == 1
    cast = run.decisions["writer_cast"]
    assert [asset["sha256"] for asset in cast["assets"]] == [photo.media_id]
    assert any("Second Person: portrait retrieval deadline elapsed" in gap for gap in cast["gaps"])


@named_passage
def test_unavailable_frozen_historical_cast_still_fails(writer_portrait):
    run, photo, sent, advance = writer_portrait
    ref = graphics_cast.portrait_asset(photo.person_id, "Source Maker", ["F01"])
    run.decisions = {**run.decisions, "writer_cast": {"assets": [ref], "gaps": []}}
    run.save(update_fields=["decisions"])
    storages["staff_media"].delete(photo.media.storage_name)
    result = advance()
    assert result["state"] == "unavailable" and result["stage"] == "C1"
    assert run.decisions["graphics_skipped_stages"]["C1"] == "cast_input_unavailable"
    assert run.decisions["writer_cast"]["assets"] == [ref]
    assert not sent


def _read_in_pool_child(output, storage_name):
    with output:
        data = graphics_references.read_staff_object_before(storage_name, time.monotonic() + 5)
        output.send((billiard.current_process().daemon, data))


def test_storage_reader_runs_in_daemonic_celery_prefork_child(editorial_storage, tmp_path):  # noqa: F811
    source = tmp_path / "staff_media" / "portrait.bin"
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(b"stored portrait")
    context = billiard.get_context("fork")
    reader, writer = context.Pipe(duplex=False)
    child = context.Process(target=_read_in_pool_child, args=(writer, source.name), daemon=True)
    child.start()
    writer.close()
    try:
        with reader:
            assert reader.poll(10)
            assert reader.recv() == (True, b"stored portrait")
    finally:
        child.join(2)
        if child.is_alive():
            child.terminate()
            child.join()
    assert child.exitcode == 0

"""Fixture-driven tests of the public announcement collection job."""
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import CollectionRun

PAGE = """
<div class="tgme_widget_message js-widget_message" data-post="twitterapiio/42">
  <div class="tgme_widget_message_text">Search is degraded.<br>Using retry.</div>
  <time datetime="2026-11-23T02:15:00+00:00"></time>
</div>
"""


def test_preview_preserves_source_time_and_message_identity():
    from monitor.provider_announcements import parse_preview

    assert parse_preview(PAGE) == [{
        "id": "42", "url": "https://t.me/twitterapiio/42",
        "published_at": "2026-11-23T02:15:00+00:00", "text": "Search is degraded.\nUsing retry.",
    }]
    with pytest.raises(ValueError, match="preview"):
        parse_preview("<html>Channel unavailable</html>")


@pytest.mark.django_db
@pytest.mark.requires_postgres
def test_poll_deduplicates_evidence_recovers_and_preserves_edits(monkeypatch):
    from monitor import provider_announcements as poll

    clock = [poll.timezone.now()]
    monkeypatch.setattr(poll, "_now", lambda: clock[0])
    monkeypatch.setattr("core.collection_state.timezone.now", lambda: clock[0])
    pages = iter([PAGE, PAGE, "", PAGE.replace("degraded", "recovering")])
    monkeypatch.setattr(poll, "fetch_preview", lambda: next(pages).encode())
    records = []

    for index in range(4):
        output = StringIO()
        if index == 2:
            with pytest.raises(CommandError, match="unavailable"):
                call_command("poll_x_provider_announcements", stdout=output)
        else:
            call_command("poll_x_provider_announcements", stdout=output)
            records.append(output.getvalue())
        clock[0] += poll.timedelta(minutes=15)

    runs = list(CollectionRun.objects.filter(job__operation="provider_announcements").order_by("started_at"))
    assert [run.status for run in runs] == ["success", "success", "failed", "success"]
    requests = [run.attempts.get().requests.get() for run in runs]
    assert requests[0].archive_id == requests[1].archive_id
    assert requests[2].archive_id is None
    assert requests[3].archive_id != requests[0].archive_id
    assert "recovering" in records[2] and "degraded" in records[0]
    assert "degraded" not in records[1]

    from core.collection_jobs import set_job_state

    job = set_job_state(runs[0].job_id, "paused")
    output = StringIO()
    call_command("poll_x_provider_announcements", stdout=output)
    assert '"status": "paused"' in output.getvalue()
    job.refresh_from_db()
    assert job.state == "paused" and job.runs.count() == 4

"""Selected-story entry must pass only saved source evidence to the package."""

from datetime import timedelta
from io import StringIO
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from core.models import OriginalContent, OriginalContentRun, Post

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.fixture
def selected_story():
    now = timezone.now()
    source = {
        "id": "2117845542021808438",
        "url": "https://x.com/i/status/2117845542021808438",
        "original_text": "Saved writing-time evidence.",
        "author_handle": "sama",
        "created_at": (now - timedelta(minutes=5)).isoformat(),
    }
    post = Post.objects.create(tweet_id=source["id"], text="Newer post text", created_at=now - timedelta(minutes=5))
    run = OriginalContentRun.objects.create(
        source_cycle_id=str(uuid4()), workflow_key="editorial-dispatch", scope_key=str(uuid4()),
        facts_as_of=now, packet_schema_version=1, snapshot={"posts": [source], "context": []},
    )
    content = OriginalContent.objects.create(
        run=run, workflow_key="social-brief", output_key=str(uuid4()), subject_key="sam-i-ram",
        story_id=uuid4(), status="prepared", attempted_at=now, brand_key_snapshot="",
        selection={"post_ids": [post.pk], "person_ids": []},
    )
    return content, run, post


def test_selected_story_passes_snapshot_not_current_post_to_orchestrator(selected_story):
    from monitor.editorial.graphics_entry import run_selected_story

    content, run, post = selected_story
    captured = []
    result = run_selected_story(content_id=content.pk, run_id=run.pk, locale="en", advance=lambda request: captured.append(request) or {"state": "queued"})
    assert result == {"state": "queued"}
    request = captured[0]
    assert request["content_id"] == content.pk
    assert request["run_id"] == run.pk
    assert request["facts_as_of"] == run.facts_as_of.isoformat()
    assert request["handoff"]["fact_items"][0]["supporting_passage"] == "Saved writing-time evidence."
    assert request["sources"][0]["id"] == post.pk
    assert request["sources"][0]["original_text"] != post.text


def test_missing_selected_post_and_wrong_run_rejected(selected_story):
    from monitor.editorial.graphics_entry import run_selected_story

    content, run, post = selected_story
    with pytest.raises(ValueError, match="run"):
        run_selected_story(content_id=content.pk, run_id=run.pk + 100, locale="en", advance=lambda request: None)
    post.delete()
    with pytest.raises(ValueError, match="missing.*post"):
        run_selected_story(content_id=content.pk, run_id=run.pk, locale="en", advance=lambda request: None)


def test_missing_packet_evidence_and_unsupported_locale_rejected(selected_story):
    from monitor.editorial.graphics_entry import run_selected_story

    content, run, _ = selected_story
    with pytest.raises(ValueError, match="locale"):
        run_selected_story(content_id=content.pk, run_id=run.pk, locale="xx", advance=lambda request: None)
    run.snapshot = {"posts": [], "context": []}
    run.save(update_fields=["snapshot"])
    with pytest.raises(ValueError, match="snapshot"):
        run_selected_story(content_id=content.pk, run_id=run.pk, locale="en", advance=lambda request: None)


def test_management_command_uses_same_entry_and_does_not_claim_publication(selected_story, monkeypatch):
    import monitor.editorial.graphics_entry as entry

    content, run, _ = selected_story
    captured = []
    monkeypatch.setattr(entry, "advance_package", lambda request: captured.append(request) or {"state": "queued"})
    out = StringIO()
    call_command("run_graphics_package", content_id=content.pk, run_id=run.pk, locale="en", stdout=out)
    assert captured[0]["content_id"] == content.pk
    assert '"state": "queued"' in out.getvalue()
    assert "published" not in out.getvalue()


def test_command_rejects_invalid_selection(selected_story):
    content, run, _ = selected_story
    with pytest.raises(CommandError):
        call_command("run_graphics_package", content_id=content.pk, run_id=run.pk + 1, locale="en", stdout=StringIO())


def test_rejects_spoofed_or_future_snapshot_and_nonprepared_story(selected_story):
    from monitor.editorial.graphics_entry import prepare_selected_story

    content, run, _ = selected_story
    source = run.snapshot['posts'][0]
    source['url'] = 'https://x.com/i/status/123'
    run.save(update_fields=['snapshot'])
    with pytest.raises(ValueError, match='URL'):
        prepare_selected_story(content_id=content.pk, run_id=run.pk, locale='en')
    source['url'] = 'https://x.com/i/status/2117845542021808438'
    source['created_at'] = (run.facts_as_of + timedelta(seconds=1)).isoformat()
    run.save(update_fields=['snapshot'])
    with pytest.raises(ValueError, match='cutoff'):
        prepare_selected_story(content_id=content.pk, run_id=run.pk, locale='en')
    source['created_at'] = (run.facts_as_of - timedelta(seconds=1)).isoformat()
    run.save(update_fields=['snapshot'])
    content.status = 'unavailable'
    content.save(update_fields=['status'])
    with pytest.raises(ValueError, match='prepared'):
        prepare_selected_story(content_id=content.pk, run_id=run.pk, locale='en')


def test_limits_default_to_owner_caps_and_never_increase_them(selected_story):
    from monitor.editorial.graphics_entry import prepare_selected_story

    content, run, _ = selected_story
    base = {'content_id': content.pk, 'run_id': run.pk, 'locale': 'en'}
    default = prepare_selected_story(**base)
    assert (default['per_story_usd'], default['daily_usd']) == ('4', '40')
    bounded = prepare_selected_story(**base, per_story_usd='1.20', daily_usd='70')
    assert (bounded['per_story_usd'], bounded['daily_usd']) == ('1.20', '40')
    with pytest.raises(ValueError, match='budget'):
        prepare_selected_story(**base, per_story_usd='NaN')


def test_no_orchestrator_is_not_a_fake_success(selected_story, monkeypatch):
    from monitor.editorial.graphics_entry import run_selected_story

    def missing_module(name):
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr('monitor.editorial.graphics_entry.import_module', missing_module)
    content, run, _ = selected_story
    with pytest.raises(RuntimeError, match='orchestration is not available'):
        run_selected_story(content_id=content.pk, run_id=run.pk, locale='en')

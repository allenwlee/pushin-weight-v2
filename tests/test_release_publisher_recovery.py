from datetime import date

import pytest

from core.release_publisher_recovery import publisher_article

ARTICLE = """<html><head><script type="application/ld+json">
{"@type":"BlogPosting","headline":"Introducing Soma-1X Lite","datePublished":"2026-11-25T15:00:00Z"}
</script></head><body><h1>Introducing Soma-1X Lite</h1>
<a href="https://x.com/AminiTech">Amini</a>
<a href="https://huggingface.co/AminiTech/Soma-1X-lite">Weights</a></body></html>"""


def test_article_confirms_exact_model_repo_publisher_and_original_date():
    actual = publisher_article(ARTICLE.encode(), "Soma-1X Lite", "AminiTech")
    assert actual.repo == "AminiTech/Soma-1X-lite"
    assert actual.day == date(2026, 11, 25)


@pytest.mark.parametrize(
    "old,new",
    [
        ("/AminiTech/Soma-1X-lite", "/spaces/AminiTech/Soma-1X-lite"),
        ("/AminiTech/Soma-1X-lite", "/OtherLab/Soma-1X-lite"),
        ("/AminiTech/Soma-1X-lite", "/AminiTech/Soma-1X-lite-instruct"),
        ("https://x.com/AminiTech", "https://x.com/AminiNews"),
        ("Introducing Soma-1X Lite", "Benchmarks for Soma-1X Lite"),
        ('"datePublished"', '"dateModified"'),
    ],
)
def test_article_rejects_wrong_identity_scope_and_dates(old, new):
    assert (
        publisher_article(
            ARTICLE.replace(old, new).encode(), "Soma-1X Lite", "AminiTech"
        )
        is None
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_cold_reporter_uses_publisher_post_and_article_then_replays_without_io(
    monkeypatch, settings
):
    from datetime import timedelta
    from types import SimpleNamespace

    from django.utils import timezone

    from core import models
    from core import release_publisher_recovery as recovery
    from core.classified_product_releases import read_publication_findings
    from tests.test_classified_product_releases import setup_cycle
    from tests.test_u18_two_role_foundation import FixedSlotTwoRoleTransport

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    state, runner, _ = setup_cycle(monkeypatch)
    text = "Amini (@AminiTech) released Soma-1X Lite this week."
    report = state.post
    report.author_handle, report.text = "SouthBrief", text
    report.created_at = timezone.now()
    report.save(update_fields=["text", "author_handle", "created_at"])
    runner.cfg.llm.classifier_pipeline = "two_role"
    runner.cfg.targeted_extraction.enabled = True

    class ReleaseTransport(FixedSlotTwoRoleTransport):
        def messages_create(self, **kwargs):
            response = super().messages_create(**kwargs)
            for decision in response["decisions"].values():
                if "post_types" in decision:
                    decision["post_types"] = ["releases_updates"]
            return response

    runner._post_fetch_clients["classification"] = ReleaseTransport()
    runner._targeted_extraction_calls["model_release_extraction"] = lambda *_: {
        "records": [
            {
                "model_name": "Soma-1X Lite",
                "organization_name": "Amini",
                "publisher_relation": "source_author",
                "novelty": "new_release",
                "source_excerpt": text,
                "categories": ["model-other"],
            }
        ]
    }
    runner._run_post_fetch([], run_id="cold-reporter-intake")
    (row,) = read_publication_findings(report.pk)
    anchor = models.EventDossierClaim.objects.get(pk=row["anchor_claim_id"])
    dossier = anchor.event_dossier_source.event_dossier
    assert not models.Product.objects.filter(display_name="Soma-1X Lite").exists()
    source_url = "https://www.amini.ai/blog-post/introducing-soma"
    published = report.created_at - timedelta(days=2)
    source_text = f"Introducing Soma-1X Lite. {source_url}"
    original = {
        "author_id": "12311223344",
        "author_handle": "AminiTech",
        "author_display_name": "Amini",
        "text": source_text,
        "id": "9998762000000001",
        "created_at": published.isoformat(),
        "author_url": "https://amini.ai",
        "tweet_url": "https://x.com/AminiTech/status/9998762000000001",
    }
    search = []
    monkeypatch.setattr(
        recovery, "_search_publisher", lambda *a: search.append(a) or [original]
    )
    expected_date = published.date() - timedelta(days=1)
    page = ARTICLE.replace("2026-11-25", expected_date.isoformat()).encode()
    from core.staff_assets import public_fetch

    monkeypatch.setattr(
        public_fetch, "fetch_before_deadline", lambda url, **_: (page, url, "text/html")
    )
    budget = SimpleNamespace(
        check=lambda: None,
        remaining=5,
        max_bytes=1024 * 1024,
        total_bytes_read=0,
        deadline=99,
    )
    assert recovery.recover_release_publisher(
        dossier, client=None, now=report.created_at, budget=budget
    )
    product = models.Product.objects.get(display_name="Soma-1X Lite")
    original_claim = models.EventDossierClaim.objects.get(
        scope_key=f"pulse-history-v1:{product.product_key}", source_locator=source_url
    )
    assert original_claim.effective_date == expected_date
    assert original_claim.event_dossier_source.post_id == original["id"]
    proof = models.EventDossierClaim.objects.get(
        scope_key="official-hf-model:AminiTech/Soma-1X-lite"
    )
    assert proof.reported_product_id == product.pk
    assert models.BrandAccount.objects.filter(
        brand=product.brand, account__author_id=original["author_id"]
    ).exists()
    assert not recovery.recover_release_publisher(
        dossier, client=None, now=report.created_at, budget=budget
    )
    assert len(search) == 1


def test_amini_visible_byline_and_multiple_hf_links():
    from core.release_publisher_recovery import publisher_article

    # Exact elements from the original publisher article, including benchmark dataset links.
    fragment = b"""<h1 class="blog_header_title u-text-style-h4">Introducing Soma-1X Lite: A 2B Model for Document Intelligence</h1>
    <div blocks-name="paragraph-8" class="resources_featured_meta-text u-text-style-small u-color-faded">November 25, 2026</div>
    <a href="https://huggingface.co/AminiTech/Soma-1X-lite">model</a>
    <a href="https://huggingface.co/datasets/allenai/olmOCR-bench">benchmark</a>
    <a href="https://huggingface.co/datasets/datalab-to/omni_parse_bench">benchmark</a>
    <a href="https://x.com/AminiTech">X</a>"""
    article = publisher_article(fragment, "Soma-1X Lite", "AminiTech")
    assert article.day == date(2026, 11, 25)
    assert article.repo == "AminiTech/Soma-1X-lite"
    conflicting = (
        fragment + b'<div class="resources_featured_meta-text">November 26, 2026</div>'
    )
    assert publisher_article(conflicting, "Soma-1X Lite", "AminiTech") is None


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_guarded_search_outage_charges_once_across_retries(monkeypatch):
    import time
    from types import SimpleNamespace

    from core.release_publisher_recovery import _search_publisher
    from monitor import enrichment_budget
    from x_monitor.x_client import XClient, XClientServerError

    monkeypatch.setenv("PULSE_STAGING_BUDGET_WINDOW_ID", "window")
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "staging")
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "fixture")
    charges = []
    monkeypatch.setattr(
        enrichment_budget, "reserve_charge", lambda **kwargs: charges.append(kwargs)
    )

    def outage(client, *_args, **_kwargs):
        client.before_request(1)
        raise XClientServerError("upstream 503")

    monkeypatch.setattr(XClient, "run_search", outage)
    budget = SimpleNamespace(
        remaining=4,
        max_bytes=1024 * 1024,
        total_bytes_read=0,
        check=lambda: None,
        deadline=time.monotonic() + 60,
        clock=time.monotonic,
    )
    for _ in range(2):
        assert _search_publisher("AminiTech", "Soma-1X Lite", budget) == []
    from core.models import SearchQuery

    assert (
        SearchQuery.objects.filter(
            plan_calls_run_id="window", query_text='from:AminiTech "Soma-1X Lite"'
        ).count()
        == 1
    )
    assert len(charges) == 1
    assert budget.remaining == 3


def test_retrospective_keeps_model_link_and_does_not_invent_a_launch_day():
    from datetime import UTC, datetime

    from core.release_publisher_recovery import (
        _announcement_effective,
        _model_repo,
        _original_post,
        _urls,
    )

    timestamp = datetime(2026, 11, 25, 12, tzinfo=UTC)
    text = "We released Soma-1X Lite on November 20. https://huggingface.co/AminiTech/Soma-1X-lite"
    raw = {"author_handle": "AminiTech", "author_id": "123", "text": text}
    assert _original_post(raw, "AminiTech", "Soma-1X Lite")
    assert (
        _model_repo(_urls(raw), "Soma-1X Lite", "AminiTech") == "AminiTech/Soma-1X-lite"
    )
    assert _announcement_effective(text, timestamp) is None
    assert _announcement_effective(
        text.replace("November 20", "2026-11-20"), timestamp
    ) == {
        "effective_precision": "day",
        "effective_date": date(2026, 11, 20),
    }


@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_first_party_older_text_only_original_cannot_hide_later_repository(
    monkeypatch, settings
):
    from datetime import timedelta
    from types import SimpleNamespace

    from django.utils import timezone

    from core import models
    from core.classified_product_releases import read_publication_findings
    from core.release_publisher_recovery import recover_release_publisher
    from tests.test_classified_product_releases import setup_cycle

    state, runner, _ = setup_cycle(monkeypatch, official=True)
    now = timezone.now()
    post = state.post
    post.created_at = now
    post.save(update_fields=["created_at"])
    runner._run_post_fetch([], run_id="saved-source-author")
    (row,) = read_publication_findings(post.pk)
    anchor = models.EventDossierClaim.objects.get(pk=row["anchor_claim_id"])
    dossier = anchor.event_dossier_source.event_dossier
    older = models.Post.objects.create(
        tweet_id="9998880011",
        author=post.author,
        author_handle=post.author_handle,
        text="Introducing Qwen4.",
        created_at=now - timedelta(days=2),
    )
    budget = SimpleNamespace(
        check=lambda: None, remaining=5, max_bytes=65536, total_bytes_read=0
    )
    assert recover_release_publisher(dossier, client=None, now=now, budget=budget)
    assert models.EventDossierClaim.objects.filter(
        event_dossier_source__post=older,
        extraction_version="pulse-historical-announcement-v1",
    ).exists()
    assert not recover_release_publisher(dossier, client=None, now=now, budget=budget)
    newer = models.Post.objects.create(
        tweet_id="9998880012",
        author=post.author,
        author_handle=post.author_handle,
        text="Introducing Qwen4. https://huggingface.co/QwenOfficial/Qwen4",
        created_at=now - timedelta(days=1),
    )
    assert recover_release_publisher(dossier, client=None, now=now, budget=budget)
    assert models.EventDossierClaim.objects.filter(
        event_dossier_source__post=newer,
        scope_key="official-hf-model:QwenOfficial/Qwen4",
    ).exists()
    assert not models.EventDossierClaim.objects.filter(
        event_dossier_source__post=newer,
        extraction_version="pulse-historical-announcement-v1",
    ).exists()
    assert not recover_release_publisher(dossier, client=None, now=now, budget=budget)

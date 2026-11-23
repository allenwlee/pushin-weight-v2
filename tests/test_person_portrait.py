"""Drive the actual research method with offline HTML, an original photo and fake HTTP."""

import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Event

import pytest
from django.db import close_old_connections
from django.utils import timezone

from core.models import Person, PersonMedia, StaffCollectionWork, StaffProviderRequest
from core.staff_assets import person_portrait as portrait
from core.staff_assets.person_portrait_sources import read_page
from monitor.editorial import providers

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]

NAME = "Arthur Mensch"
PASSAGE = "Arthur Mensch is the CEO of Mistral."
PAGE = "https://leadership.example/people/arthur"
PHOTO = "https://leadership.example/images/headshot.webp"
# Existing project Arthur Mensch image. The HTML, response, caption and credit
# in these tests are controlled fixture data, not claims about the real source.
DATA = (Path(__file__).parent / "fixtures/person_portrait/arthur.webp").read_bytes()
ALT = "Portrait of Arthur Mensch"
HTML = (
    f"<html><title>{NAME} | Leadership</title><main><h1>{NAME}</h1><p>{PASSAGE}</p>"
    f"<p>Arthur Mensch was a researcher at OtherLab from 2018 to 2023.</p>"
    f'<figure><img src="{PHOTO}" alt="{ALT}"><figcaption>Photo by Test Studio.</figcaption></figure>'
    f'<a href="https://x.com/arthurmensch">{NAME} on X</a></main></html>'
).encode()


@pytest.fixture
def run(settings, tmp_path, monkeypatch):
    settings.STORAGES = {
        **settings.STORAGES,
        "staff_media": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path)},
        },
    }
    person = Person.objects.create()
    work = StaffCollectionWork.objects.create(
        person=person,
        state="running",
        lease_token=uuid.uuid4(),
        lease_expires_at=timezone.now() + timedelta(minutes=5),
        fingerprint="a" * 64,
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    monkeypatch.setenv("EXA_API_KEY", "fake")
    inputs = {
        "person": person,
        "subject": NAME,
        "evidence": {
            "passage": PASSAGE,
            "source_url": PAGE,
            "affiliation": {"organization": "Mistral"},
        },
        "work": work,
    }
    return work, inputs


def fake_sources(monkeypatch, *, answer=None, urls=None):
    records = {"search": [], "fetch": [], "assessment": []}
    urls = {PAGE: HTML, PHOTO: DATA} if urls is None else urls

    def fetch(url, *, max_bytes, deadline):
        records["fetch"].append((url, deadline))
        item = urls[url]
        assert len(item) <= max_bytes
        return item, url, "text/html" if item.startswith(b"<") else "image/webp"

    def search(query, *, api_key, timeout):
        records["search"].append(query)
        return {"query": query, "results": [{"url": PAGE}], "estimated_usd": "0.007"}

    def model(endpoint, key, body, *, timeout):
        records["assessment"].append(body)
        fields = {
            "identity": "supported",
            "identity_quote": PASSAGE,
            "image": "individual_portrait",
            "attribution_quote": ALT,
            "organization": "Mistral",
            "title": "CEO",
            "affiliation_status": "current",
            "affiliation_quote": PASSAGE,
            "image_credit": "Test Studio",
            "image_license": "CC0",
        } | (answer or {})
        response = {
            "model": body["model"],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.001},
            "choices": [
                {"finish_reason": "stop", "message": {"content": json.dumps(fields)}}
            ],
        }
        return 200, json.dumps(response).encode()

    monkeypatch.setattr(portrait, "fetch_before_deadline", fetch)
    monkeypatch.setattr(portrait, "search_exa_query", search)
    monkeypatch.setattr(providers, "https_request", model)
    return records


def test_original_portrait_and_single_source_and_pixel_assessment(run, monkeypatch):
    work, inputs = run
    calls = fake_sources(monkeypatch)
    result = portrait.research_general_portrait(**inputs)
    assert result["status"] == "complete", result
    assert result["evidence"][0]["affiliation"] == {
        "organization": "Mistral",
        "title": "CEO",
        "status": "current",
    }
    row = PersonMedia.objects.get(pk=result["asset_ids"][0])
    assert row.media_id == hashlib.sha256(DATA).hexdigest()
    assert (
        row.individual_portrait
        and row.source_verified
        and row.suitability == "approved"
    )
    assert row.evidence["credit"] == "Test Studio" and row.evidence["license"] is None
    assert row.reuse_status == "unknown" and row.discovery_provider == "story_source"
    assert row.source_url == PAGE and row.original_url == PHOTO
    assert not any(
        event.get("event") == "owner_confirmed_media" for event in row.review_history
    )
    assert [entry[0] for entry in calls["fetch"]] == [PAGE, PHOTO]
    assert not calls["search"] and len(calls["assessment"]) == 1
    attachments = calls["assessment"][0]["messages"][-1]["content"]
    assert attachments[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert PASSAGE in attachments[0]["text"] and ALT in attachments[0]["text"]
    assert result["counters"]["person_research_llm_calls"] == 1
    assert (
        result["costs"][0]["billed_usd"] == "0.001"
        and result["costs"][0]["reserved_usd"]
    )
    again = portrait.research_general_portrait(**inputs)
    assert (
        again["asset_ids"] == [row.pk]
        and len(calls["assessment"]) == 1
        and len(calls["fetch"]) == 2
    ), again
    assert StaffProviderRequest.objects.filter(work=work).count() == 3


@pytest.mark.parametrize(
    "flags,expected",
    [
        ({"image": "group"}, "needs_evidence"),
        ({"image": "logo"}, "needs_evidence"),
        ({"image": "placeholder"}, "needs_evidence"),
        ({"attribution_quote": "Arthur in another article"}, "needs_evidence"),
        ({"identity": "unresolved"}, "identity_unresolved"),
    ],
)
def test_ambiguous_or_unsuitable_never_becomes_cast(run, monkeypatch, flags, expected):
    _, inputs = run
    calls = fake_sources(monkeypatch, answer=flags)
    result = portrait.research_general_portrait(**inputs)
    assert result["status"] == expected and result["gaps"]
    assert len(calls["assessment"]) == 1 and not PersonMedia.objects.exists()


def test_source_and_search_pages_share_one_cap_and_deadline(run, monkeypatch):
    _, inputs = run
    first, second = "https://site.example/story", "https://site.example/interview"
    inputs["evidence"]["source_urls"] = [first, second]
    inputs["evidence"]["affiliation"] = {"brand_id": "mistral"}
    inputs["evidence"]["source_url"] = first
    calls = fake_sources(
        monkeypatch,
        urls={
            first: b"<p>Article</p>",
            second: b"<p>No image</p>",
            PAGE: HTML,
            PHOTO: DATA,
        },
    )
    result = portrait.research_general_portrait(**inputs)
    assert result["status"] == "complete", result
    assert calls["search"] == ['"Arthur Mensch" "Mistral"']
    assert [entry[0] for entry in calls["fetch"]] == [first, second, PAGE, PHOTO]
    assert len({entry[1] for entry in calls["fetch"]}) == 1
    assert (
        result["counters"]["pages_fetched"] == 3
        and result["counters"]["images_downloaded"] == 1
    )
    exa = next(c for c in result["costs"] if c["operation"] == "portrait_exa")
    assert exa["estimated_usd"] == "0.007" and exa["billed_usd"] is None


def test_only_page_title_and_filename_insufficient():
    html = f'<title>Reporter describes {NAME} visiting</title><img src="arthur-mensch.jpg" alt="">'.encode()
    assert (
        read_page(html, name=NAME, requested_url=PAGE, final_url=PAGE)["candidate"]
        is None
    )


def test_jobs_only_extracts_sourced_dates_without_fetching_or_sending_images(
    run, monkeypatch
):
    _, inputs = run
    claim = {
        "quote": "Arthur Mensch was a researcher at OtherLab from 2018 to 2023.",
        "organization": "OtherLab",
        "title": "researcher",
        "status": "former",
        "start_date": "2018",
        "end_date": "2023",
    }
    calls = fake_sources(
        monkeypatch,
        answer={"image": "absent", "attribution_quote": "", "job_history": [claim]},
    )
    result = portrait.research_general_portrait(**inputs, jobs=True, portrait=False)
    assert result["status"] == "complete", result
    assert result["evidence"][-1]["affiliation"]["end_date_precision"] == "year"
    assert result["evidence"][-1]["affiliation"]["end_date"] == "2023"
    assert result["asset_ids"] == [] and result["counters"]["images_downloaded"] == 0
    assert [item[0] for item in calls["fetch"]] == [PAGE]
    assert isinstance(calls["assessment"][0]["messages"][-1]["content"], str)
    assert not PersonMedia.objects.exists()


def test_paid_timeout_is_preserved_and_never_resent(run, monkeypatch):
    _, inputs = run
    inputs["evidence"]["source_url"] = ""
    issued = []

    def timed_out(*args, **kwargs):
        issued.append(args)
        raise TimeoutError()

    monkeypatch.setattr(portrait, "search_exa_query", timed_out)
    first = portrait.research_general_portrait(**inputs)
    second = portrait.research_general_portrait(**inputs)
    assert (
        first["costs"][0]["state"] == "needs_review"
        and second["status"] == "needs_review"
    )
    assert len(issued) == 1 and not PersonMedia.objects.exists()


def test_enabled_file_comparison_is_independent_of_search(run, monkeypatch):
    _, inputs = run
    calls = fake_sources(monkeypatch)
    compared = []

    def compare(person, data, sha):
        compared.append(sha)
        assert data == DATA
        return {
            "reference_sha256": "b" * 64,
            "candidate_sha256": sha,
            "scores": [62.3],
            "matched": True,
        }

    monkeypatch.setattr(portrait, "_compare_face", compare)
    result = portrait.research_general_portrait(**inputs, facematch=True)
    assert result["status"] == "complete" and len(compared) == 1 and not calls["search"]
    source = PersonMedia.objects.get(pk=result["asset_ids"][0]).evidence[
        "source_evidence"
    ]
    assert source["face_comparison"]["scores"] == [62.3]
    assert source["assessment"]["attribution_quote"] == ALT


@pytest.mark.django_db(transaction=True)
def test_overlapping_requests_reserve_one_physical_search(run):
    work, _ = run
    entered, release = Event(), Event()
    sends = []

    def search():
        close_old_connections()
        try:

            def send():
                sends.append(1)
                entered.set()
                assert release.wait(4)
                return {"results": []}

            return portrait._once(work, "portrait_exa", {"query": NAME}, send)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(search)
        assert entered.wait(4)
        try:
            with pytest.raises(portrait.AmbiguousRequest):
                executor.submit(search).result(4)
        finally:
            release.set()
        assert first.result(4) == {"results": []}
    assert sends == [1]


def test_total_page_allowance_prevents_a_fourth_download_or_pointless_search(
    run, monkeypatch
):
    _, inputs = run
    urls = [f"https://leadership.example/page/{i}" for i in range(5)]
    inputs["evidence"]["source_urls"] = urls
    calls = fake_sources(monkeypatch, urls={url: b"<p>Overview</p>" for url in urls})
    result = portrait.research_general_portrait(**inputs)
    assert [entry[0] for entry in calls["fetch"]] == urls[:3]
    assert not calls["search"] and not calls["assessment"]
    assert (
        result["status"] == "needs_evidence"
        and result["counters"]["page_requests"] == 3
    )


def test_expired_retrieval_window_survives_worker_restart(run, monkeypatch):
    work, inputs = run
    calls = fake_sources(monkeypatch)
    # Simulate an already completed, unrelated first page in this receipt.
    req = StaffProviderRequest.objects.create(
        work=work,
        person=work.person,
        provider="portrait_page",
        fingerprint="f" * 64,
        run_id=uuid.uuid4(),
        state="complete",
        response={"gap": "failed"},
    )
    StaffProviderRequest.objects.filter(pk=req.pk).update(
        created_at=timezone.now() - timedelta(seconds=25)
    )
    result = portrait.research_general_portrait(**inputs)
    assert "retrieval_deadline" in result["gaps"]
    assert not calls["search"] and not calls["fetch"] and not calls["assessment"]


def test_a_second_story_cannot_resubmit_an_ambiguous_paid_search(run, monkeypatch):
    work, inputs = run
    inputs["evidence"].pop("source_url")
    sends = []

    def timeout(*args, **kwargs):
        sends.append(1)
        raise TimeoutError()

    monkeypatch.setattr(portrait, "search_exa_query", timeout)
    assert portrait.research_general_portrait(**inputs)["status"] == "needs_review"
    second = StaffCollectionWork.objects.create(
        person=work.person,
        fingerprint="c" * 64,
        state="running",
        lease_token=uuid.uuid4(),
        lease_expires_at=timezone.now() + timedelta(minutes=5),
    )
    result = portrait.research_general_portrait(**{**inputs, "work": second})
    assert result["status"] == "needs_review" and len(sends) == 1
    assert result["counters"]["search_requests"] == 0


def test_exa_receipt_is_a_provider_estimate():
    from monitor.editorial.graphics_search import search_exa_query

    result = search_exa_query(
        "portrait",
        api_key="fake",
        transport=lambda *_: b'{"results":[],"costDollars":{"total":0.009}}',
    )
    assert result["estimated_usd"] == "0.009" and "billed_usd" not in result


def test_new_page_must_disambiguate_namesakes_even_for_a_resolved_story_subject(
    run, monkeypatch
):
    from core.models import PersonName

    work, inputs = run
    for person in (work.person, Person.objects.create()):
        PersonName.objects.create(
            person=person, full_name=NAME, locale_id="und", fingerprint="c" * 64
        )
    calls = fake_sources(monkeypatch)
    result = portrait.research_general_portrait(**inputs)
    assert result["status"] == "identity_unresolved"
    assert "source_does_not_disambiguate_namesakes" in result["gaps"]
    assert len(calls["assessment"]) == 1 and not PersonMedia.objects.exists()


def test_slow_dns_does_not_start_http_after_aggregate_deadline(monkeypatch):
    import time

    from core.staff_assets import public_fetch

    entered, release = Event(), Event()

    def resolve(url):
        from urllib.parse import urlsplit

        entered.set()
        assert release.wait(3)
        return urlsplit(url), 443, ["93.184.216.34"]

    network = []
    monkeypatch.setattr(public_fetch, "public_addresses", resolve)
    monkeypatch.setattr(
        public_fetch.urllib3, "HTTPSConnectionPool", lambda **kw: network.append(kw)
    )
    try:
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            public_fetch.fetch_before_deadline(
                PAGE, max_bytes=100, deadline=start + 0.15
            )
        assert entered.is_set() and time.monotonic() < start + 1.0
    finally:
        release.set()
    assert not network

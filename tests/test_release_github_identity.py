from datetime import date

import httpx
import pytest

from core.release_publisher_recovery import publisher_article


def article_links(*links, product="Model One"):
    return publisher_article(
        (
            f'<h1 class="blog_header_title">Introducing {product}</h1>'
            '<div class="resources_featured_meta-text">November 25, 2026</div>'
            '<a href="https://x.com/Lab">X</a>' + "".join(links)
        ).encode(),
        product,
        "Lab",
    )


def test_github_only_publisher_profile_survives_when_preview_has_no_repo():
    page = article_links(
        '<a class="social-link" href="https://github.com/StartLuxLabs" aria-label="StartLux 官方 GitHub">GitHub</a>',
        '<a href="https://github.com/StartLuxLabs/StartLux-Decision">Separate offering</a>',
        product="StartLux-V1.0-27B-Preview",
    )
    assert page and page.github_profile == "StartLuxLabs" and page.github_repo is None


def test_article_identifies_github_org_and_exact_repo_independently():
    page = article_links(
        '<a class="social-link" href="https://github.com/LabOrg" aria-label="官方 GitHub">GitHub</a>',
        '<a href="https://github.com/LabOrg/Model-One">Code</a>',
        '<a href="https://github.com/LabOrg/Model-One-Flash">Other release</a>',
    )
    assert page and page.day == date(2026, 11, 25)
    assert page.github_profile == "LabOrg"
    assert page.github_repo == "LabOrg/Model-One"
    assert page.repo is None


@pytest.mark.parametrize(
    "bad",
    [
        "https://github.com/LabOrg/Model-One-Flash",
        "https://github.com/Other/Model-One",
        "https://github.com/LabOrg/Model-One/issues",
        "https://github.com.evil.example/LabOrg/Model-One",
    ],
)
def test_related_or_third_party_repos_cannot_claim_this_product(bad):
    page = article_links(
        '<a rel="me" href="https://github.com/LabOrg">GitHub</a>',
        '<a href="https://huggingface.co/Lab/Model-One">Model</a>',
        f'<a href="{bad}">Related</a>',
    )
    assert page and page.github_profile == "LabOrg" and page.github_repo is None


@pytest.mark.requires_postgres
@pytest.mark.django_db
@pytest.mark.parametrize(
    "scope, owner_type, repo_name, expected",
    [
        ("publisher", "Organization", None, (True, False)),
        ("repository", "Organization", "Model-One", (True, True)),
        ("repository", "Organization", "Model-One-Flash", (True, False)),
        ("repository", "User", "Model-One", (False, False)),
    ],
)
def test_github_consumes_saved_evidence_even_after_exhausted_first_budget(
    scope, owner_type, repo_name, expected
):
    from core import models
    from core.collection_budgets import invocation_budget
    from core.event_dossiers import add_claim
    from core.release_chart_handoff import resolve_release
    from core.release_github_identity import discover_github_release
    from tests.product_factory import product_type_fields
    from tests.test_release_chart_metric_collection import release_for

    brand = models.Brand.objects.create(nickname="launchlab", display_name="Launch Lab")
    product = models.Product.objects.create(
        brand=brand,
        display_name="Model One",
        **product_type_fields(models.Product, "model-other"),
    )
    dossier, announcement = release_for(product)
    for kind, github_path in [("publisher", "LabOrg")] + (
        [("repository", "LabOrg/Model-One")] if scope == "repository" else []
    ):
        url = "https://github.com/" + github_path
        add_claim(
            announcement.event_dossier_source_id,
            claim_kind="release_context",
            scope_key="github-" + kind + ":" + github_path.lower(),
            assertion_text=url,
            source_excerpt=url,
            source_locator="https://example.org/launch",
            extraction_version="pulse-github-source-v1",
            reported_brand_id=brand.pk,
            reported_product_id=product.pk,
        )
    release = resolve_release(dossier.pk)
    owner = {
        "login": "LabOrg",
        "id": 90091,
        "type": owner_type,
        "html_url": "https://github.com/LabOrg",
    }

    def respond(request):
        assert "authorization" not in request.headers
        if request.url.path == "/users/LabOrg":
            return httpx.Response(200, json=owner)
        assert request.url.path == "/repos/LabOrg/Model-One"
        return httpx.Response(
            200,
            json={
                "id": 80081,
                "full_name": "LabOrg/" + repo_name,
                "owner": owner,
                "fork": False,
                "private": False,
                "html_url": "https://github.com/LabOrg/" + repo_name,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        exhausted = invocation_budget(client, requests=1, seconds=3)
        exhausted.remaining = 0
        assert not discover_github_release(release, budget=exhausted)
        assert not models.BrandAccount.objects.filter(brand=brand).exists()
        budget = invocation_budget(client, requests=3, seconds=3)
        discover_github_release(release, budget=budget)
        links = models.BrandAccount.objects.filter(
            brand=brand,
            role_id="official",
            account__data_source_id="github",
            account__external_identifier="90091",
        )
        maps = models.SourceSubjectMapping.objects.filter(
            purpose="catalog",
            source_id="github",
            subject__product=product,
            external_identifier="80081",
        )
        assert (links.exists(), maps.exists()) == expected
        if scope == "publisher" or expected == (True, True):
            repeat = invocation_budget(client, requests=1, seconds=3)
            assert not discover_github_release(release, budget=repeat)
            assert repeat.remaining == 1
    assert not models.CompanyAccount.objects.filter(
        account__data_source_id="github"
    ).exists()


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "previous_hf, reporter", [(False, False), (True, False), (True, True)]
)
def test_saved_official_github_announcement_enriches_dated_release_once(
    monkeypatch, settings, previous_hf, reporter
):
    from datetime import timedelta

    from django.utils import timezone

    from core import models
    from core.classified_product_releases import read_publication_findings
    from core.release_chart_collection import collect_due_release_metrics
    from core.release_publisher_recovery import recover_release_publisher
    from tests.test_classified_product_releases import setup_cycle

    state, runner, transport = setup_cycle(monkeypatch, official=True)
    report = state.post
    now = timezone.now()
    publisher = report.author
    publisher_handle = report.author_handle
    if reporter:
        report.text = "Qwen (@QwenOfficial) released Qwen4 weights today."
        report.author = models.Account.objects.create(
            author_id="87771", handle="NewsDesk"
        )
        report.author_handle = "NewsDesk"
        report.tweet_url = "https://x.com/NewsDesk/status/73110010"
        transport.document["entities"][0]["evidence"] = report.text
        packet = transport.document["release_findings"]["findings"][0]
        packet["assertions"][0]["source_excerpt"] = report.text
        packet["issuer_evidence"]["source_excerpt"] = report.text
        report.save(update_fields=["text", "author", "author_handle", "tweet_url"])
    report.created_at = now
    report.save(update_fields=["created_at"])
    runner._run_post_fetch([], run_id="dated-github-release")
    (finding,) = read_publication_findings(report.pk)
    anchor = models.EventDossierClaim.objects.get(pk=finding["anchor_claim_id"])
    dossier = anchor.event_dossier_source.event_dossier
    models.Post.objects.create(
        tweet_id="73110011",
        author=publisher,
        author_handle=publisher_handle,
        text="Introducing Qwen4."
        + (" https://huggingface.co/QwenOfficial/Qwen4" if previous_hf else ""),
        created_at=now - timedelta(days=3),
    )
    if reporter:
        from core.classified_product_releases import replay_saved_publisher
        from tests.product_factory import product_type_fields

        # This review case starts with a confirmed Product on a third-party
        # report. Its own account cannot establish the GitHub publisher.
        chosen = models.Product.objects.create(
            brand_id="qwen",
            display_name="Qwen4",
            **product_type_fields(models.Product, "model-llm"),
        )
        models.PostBrandProduct.objects.create(
            post=report,
            brand_id="qwen",
            product=chosen,
            observed_name="Qwen4",
            source_evidence={"original_release_claim": str(anchor.pk)},
            verification_policy_version="fixture-qualified-source-v1",
        )
        assert (
            replay_saved_publisher(finding["finding"], report)["issuer_evidence"][
                "observed_handle"
            ]
            == "qwenofficial"
        )
    assert recover_release_publisher(dossier, client=None, budget=None, now=now)
    claims = models.EventDossierClaim.objects.filter(
        event_dossier_source__event_dossier=dossier
    )
    date_claims = claims.filter(extraction_version="pulse-historical-announcement-v1")
    old_dates = list(date_claims.values_list("pk", "effective_at", "effective_date"))
    assert len(old_dates) == 1
    models.Post.objects.create(
        tweet_id="73110012",
        author=publisher,
        author_handle=publisher_handle,
        text="Introducing Qwen4. https://github.com/QwenLab/Qwen4-Flash",
        created_at=now - timedelta(days=2),
    )
    if previous_hf and not reporter:
        profile_post = models.Post.objects.create(
            tweet_id="73110014",
            author=publisher,
            author_handle=publisher_handle,
            author_url="https://github.com/QwenLab",
            text="Introducing Qwen4.",
            created_at=now - timedelta(days=2, hours=1),
        )
        assert recover_release_publisher(dossier, client=None, budget=None, now=now)
        assert (
            claims.get(scope_key="github-publisher:qwenlab").event_dossier_source.post
            == profile_post
        )
    later = models.Post.objects.create(
        tweet_id="73110013",
        author=publisher,
        author_handle=publisher_handle,
        text="Introducing Qwen4. https://github.com/QwenLab/Qwen4",
        created_at=now - timedelta(days=1),
    )
    if previous_hf and not reporter:
        from core.event_dossiers import ProductReleaseInput
        from tests.test_event_dossiers import review

        selected = date_claims.get().reported_product
        review(
            dossier,
            anchor,
            review_state="confirmed",
            product_release=ProductReleaseInput(
                observed_name="Qwen4",
                product_key=selected.product_key,
                disclosure_state="announced",
            ),
        )
        dossier.refresh_from_db()
        saved_review = dossier.current_review_id
    calls = []
    owner = {
        "type": "Organization",
        "id": 9111,
        "login": "QwenLab",
        "html_url": "https://github.com/QwenLab",
        "twitter_username": publisher_handle,
    }

    def github_only(request):
        calls.append(request.url.path)
        if request.url.path == "/users/QwenLab":
            return httpx.Response(200, json=owner)
        assert request.url.path == "/repos/QwenLab/Qwen4"
        return httpx.Response(
            200,
            json={
                "private": False,
                "fork": False,
                "id": 8122,
                "owner": owner,
                "full_name": "QwenLab/Qwen4",
                "html_url": "https://github.com/QwenLab/Qwen4",
            },
        )

    def only_github(release, budget, result, now):
        from core.release_github_identity import discover_github_release

        discover_github_release(release, budget=budget)

    monkeypatch.setattr(
        "core.release_chart_collection._discover_public_catalogs", only_github
    )
    monkeypatch.setattr(
        "core.release_publisher_recovery._search_publisher",
        lambda *args: pytest.fail("unexpected paid publisher search"),
    )
    monkeypatch.setattr(
        "core.release_provider_identity.discover_verified_hf_model",
        lambda *a, **kw: False,
    )
    settings.BENCHMARK_COLLECTION_ENABLED = False
    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    with httpx.Client(transport=httpx.MockTransport(github_only)) as client:
        for _ in range(2):
            collect_due_release_metrics(
                client=client,
                dossier_ids=[dossier.pk],
                max_seconds=10,
                confirm_identities=True,
            )
    claim = claims.get(
        extraction_version="pulse-github-source-v1",
        scope_key="github-repository:qwenlab/qwen4",
    )
    assert claim.event_dossier_source.post == later
    assert (
        models.SourceSubjectMapping.objects.filter(
            source_id="github",
            external_identifier="8122",
            subject__product_id=claim.reported_product.product_key,
        ).count()
        == 1
    )
    assert (
        list(date_claims.values_list("pk", "effective_at", "effective_date"))
        == old_dates
    )
    assert calls == ["/users/QwenLab", "/repos/QwenLab/Qwen4"]
    if previous_hf and not reporter:
        dossier.refresh_from_db()
        assert dossier.current_review_id == saved_review
    if not previous_hf:
        later_hf = models.Post.objects.create(
            tweet_id="73110015",
            author=publisher,
            author_handle=publisher_handle,
            text="Introducing Qwen4. https://huggingface.co/QwenOfficial/Qwen4",
            created_at=now - timedelta(hours=1),
        )
        assert recover_release_publisher(dossier, client=None, budget=None, now=now)
        assert (
            claims.get(
                scope_key="official-hf-model:QwenOfficial/Qwen4"
            ).event_dossier_source.post
            == later_hf
        )
        assert (
            list(date_claims.values_list("pk", "effective_at", "effective_date"))
            == old_dates
        )

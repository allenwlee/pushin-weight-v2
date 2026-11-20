import json
from pathlib import Path

import pytest

from core.product_release_hf_collection import family_from_collection


@pytest.fixture
def collection():
    path = Path(__file__).parent / "fixtures/pulse/hf-botpsy-collection.json"
    return json.loads(path.read_bytes())


def test_saved_botpsy_collection_names_both_models(collection):
    for repo in ('qvac/BotPsy-0.8B', 'qvac/BotPsy-0.8B-GGUFs'):
        assert family_from_collection(collection, repo)['name'] == 'BotPsy'


@pytest.mark.parametrize('change', ['mixed', 'other_owner', 'not_member', 'generic', 'non_model'])
def test_collection_does_not_name_a_family_without_a_single_publisher_line(collection, change):
    repo = 'qvac/BotPsy-0.8B'
    if change == 'mixed':
        collection['items'][1]['id'] = 'qvac/OtherModel'
    elif change == 'other_owner':
        collection['owner']['name'] = 'someone-else'
    elif change == 'not_member':
        repo = 'qvac/BotPsy-3B'
    elif change == 'generic':
        collection['title'] = 'Featured models'
    else:
        collection['items'][1]['type'] = 'dataset'
    assert family_from_collection(collection, repo) is None


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("mixed,interrupted,stopped", [(False, False, False), (True, False, False), (False, True, False), (False, False, True)])
def test_saved_collection_capture_applies_publisher_family_without_new_model_calls(collection, mixed, interrupted, stopped, monkeypatch, settings, tmp_path):
    import httpx
    from django.db.models import F

    from core import models
    from core.collection_capture import observation_object_documents
    from core.product_release_acquisition import execute_hf_name_search, queue_hf_name_search
    from core.product_release_dossiers import record_release_report
    from core.product_release_hf_collection import execute_collection

    if mixed:
        collection["items"][1]["id"] = "qvac/OtherModel"
    models.DataSource.objects.get_or_create(pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"})
    brand = models.Brand.objects.create(nickname="qvac")
    repo = "qvac/BotPsy-0.8B"
    product = models.Product.objects.create(repo_id=repo, display_name="BotPsy-0.8B", brand=brand,
                                            product_type=models.ProductType.objects.get(code="model-llm"))
    post = models.Post.objects.create(tweet_id="hf-collection-release", text=f"We release BotPsy https://huggingface.co/{repo}")
    dossier, _, _ = record_release_report(post=post, record={"model_name": "BotPsy", "source_url": f"https://huggingface.co/{repo}"},
        release_identity="hf-collection-release", observed_name="BotPsy", source_url=f"https://huggingface.co/{repo}",
        maturity_code="unknown", release_value=None, release_precision="unknown", extraction_version="test")
    claim = models.EventDossierClaim.objects.get(event_dossier_source__event_dossier=dossier, claim_kind_reference__code="release_report")
    calls = []
    def respond(request):
        calls.append(str(request.url))
        if request.url.path.startswith("/api/models/"):
            return httpx.Response(200, json={"id": repo, "author": "qvac", "sha": "a" * 40})
        if request.url.path == "/api/collections":
            assert request.url.params["owner"] == "qvac" and request.url.params["item"] == "models/" + repo
            return httpx.Response(200, json=[{"owner": {"name": "qvac"}, "slug": collection["slug"], "title": "BotPsy"}])
        assert request.url.path == "/api/collections/" + collection["slug"]
        return httpx.Response(200, json=collection)
    client = httpx.Client(transport=httpx.MockTransport(respond))
    execute_hf_name_search(queue_hf_name_search(claim.pk).pk, client=client)
    job = models.CollectionJob.objects.get(targets__target_role="model_collection")
    if stopped:
        from monitor import pulse_control
        monkeypatch.setenv("X_MONITOR_CLASSIFIER_PIPELINE", "compressed8_pulse_v1")
        settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
        settings.PULSE_CONTROL_R2_BUCKET = ""
        pulse_control.initialize(directory=tmp_path, state="stopped", actor="fixture", reason="test")
    if interrupted:
        from datetime import timedelta
        from django.utils import timezone
        from core import collection_state
        monkeypatch.setattr(collection_state, "finish_run", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("crash")))
        with pytest.raises(RuntimeError, match="crash"):
            execute_collection(job.pk, client=client)
        run = models.CollectionRun.objects.get(job=job)
        models.CollectionRun.objects.filter(pk=run.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        monkeypatch.undo()
    result = execute_collection(job.pk, client=client)
    assert result["outcome"] == "found" and result["physical_requests"] == (0 if interrupted else 2)
    observation = models.CollectionObservation.objects.get(projection_kind="hf-release-collection-v1")
    assert observation_object_documents(observation)[0] == collection
    if stopped:
        assert not models.ProductGroupMembership.objects.filter(product=product).exists()
        row = pulse_control.read_status()
        pulse_control.request_state("running", expected_revision=row["desired_revision"], actor="fixture", reason="test")
        from core.product_release_acquisition import drain_due_hf_acquisitions
        recovered = drain_due_hf_acquisitions(client=client, execute=True, job_ids=[str(job.pk)])
        assert recovered["provider_calls"] == 0
        assert recovered["jobs"][0]["integration"]["status"] == "complete"
    memberships = models.ProductGroupMembership.objects.filter(product=product, group__group_kind="family",
        taxonomy_version_id=F("group__rule_taxonomy_version_id"), membership_status="included")
    if mixed:
        assert not memberships.exists()
        assert not dossier.sources.filter(collection_observation=observation).exists()
    else:
        assert memberships.get().group.name == "BotPsy"
        assert dossier.sources.filter(collection_observation=observation).exists()
    assert execute_collection(job.pk, client=client)["physical_requests"] == 0
    assert len(calls) == 3

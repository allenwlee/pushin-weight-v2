"""Release evidence follows saved classification, independent of search source."""

import pytest

from core.models import (
    EventDossier,
    EventDossierClaim,
    PostBrandSignal,
    PostTypeKey,
    RareTypeSearchHit,
    SentimentKey,
    TargetedExtractionState,
)
from monitor.cycle import CycleRunner
from scripts.backfill_targeted import requirements
from tests.test_post_enrichment_queue import _cfg, _classification_results, _state
from tests.test_rare_type_commands import _hits, _mark_kept_and_link
from x_monitor import attribution, reattribute, translator

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

QUOTE = "Nanbeige released Nanbeige4.3-33B. Qwen is a comparator; the 33B model teaches an upcoming 3B model."


@pytest.mark.parametrize("origin", ["ordinary", "special-events"])
@pytest.mark.parametrize("path", ["new-classification", "saved-replay"])
def test_real_enrichment_and_replay_accept_the_same_release(monkeypatch, origin, path):
    state = _state("release-routing")
    state.post.text = "DeepSeek comparison and a quoted release announcement"
    state.post.quoted_text = QUOTE
    state.post.save(update_fields=["text", "quoted_text"])
    if origin == "special-events":
        _mark_kept_and_link(_hits(state.pk)[0], state.post)
    else:
        assert not RareTypeSearchHit.objects.exists()
    cfg = _cfg()
    cfg.targeted_extraction.enabled = True
    cfg.targeted_extraction.max_calls_per_cycle = 1
    seen = []

    def extract(system, user, model, max_tokens):
        assert QUOTE in user
        seen.append(user)
        return {
            "records": [
                {
                    "organization_name": "Nanbeige",
                    "model_name": "Nanbeige4.3-33B",
                    "version": "4.3-33B",
                    "release_channel": "stable",
                    "release_precision": "unknown",
                }
            ]
        }

    runner = CycleRunner(
        cfg=cfg, _targeted_extraction_calls={"model_release_extraction": extract}
    )
    if path == "saved-replay":
        state.classification_status = "succeeded"
        state.save(update_fields=["classification_status"])
        PostBrandSignal.objects.create(
            post=state.post,
            brand_id="deepseek",
            post_type=PostTypeKey.objects.get(key="releases_updates"),
            sentiment=SentimentKey.objects.get(key="neutral"),
        )
        assert set(requirements(state.post, cfg)) == {"model_release_extraction"}
        result = runner._replay_targeted_extractions(post_ids={state.pk})
        assert result["calls"] == 1
    else:
        monkeypatch.setattr(
            reattribute, "build_translator_client_from_env", lambda *a, **k: object()
        )
        monkeypatch.setattr(
            reattribute, "build_classifier_client_from_env", lambda *a, **k: object()
        )
        monkeypatch.setattr(
            translator,
            "translate_batch_pragmatics",
            lambda tweets, *a, **k: [
                {
                    "tweet_id": t["tweet_id"],
                    "text_en": t["text"],
                    "text_zh_cn": "引述南北阁模型发布，并对比其他模型。",
                    "en_equivalent": "The announcement introduces a model for comparison.",
                    "cn_equivalent": "这次发布提供了新的模型比较对象。",
                    "lang_detected": "en",
                }
                for t in tweets
            ],
        )
        monkeypatch.setattr(
            attribution,
            "classify_batch_pragmatics_full",
            lambda tweets, *a, **k: _classification_results(tweets),
        )
        result = runner._run_post_fetch(
            [], run_id="release-routing", post_ids={state.pk}
        )
        assert result["n_targeted_extraction_calls"] == 1
        state.refresh_from_db()
        assert state.classification_status == "succeeded"
    dossier = EventDossier.objects.get(event_kind_reference__code="product_release")
    claim = EventDossierClaim.objects.get(event_dossier_source__event_dossier=dossier)
    assert claim.reported_brand_id is None
    assert claim.reported_brand_discovery_candidate.observed_name == "Nanbeige"
    assert dossier.current_review_id is None
    assert len(seen) == 1
    assert TargetedExtractionState.objects.get(post=state.post).status == "succeeded"
    replay = runner._replay_targeted_extractions(post_ids={state.pk})
    assert replay["calls"] == 0
    assert len(seen) == 1
    assert EventDossierClaim.objects.count() == 1


@pytest.mark.parametrize("stop", ["disabled", "budget", "deadline", "unclassified"])
def test_release_replay_respects_existing_dispatch_guards(stop):
    from unittest.mock import Mock

    state = _state("release-routing-guard")
    state.classification_status = "pending" if stop == "unclassified" else "succeeded"
    state.save(update_fields=["classification_status"])
    PostBrandSignal.objects.create(
        post=state.post,
        brand_id="deepseek",
        post_type=PostTypeKey.objects.get(key="releases_updates"),
        sentiment=SentimentKey.objects.get(key="neutral"),
    )
    cfg = _cfg()
    cfg.targeted_extraction.enabled = stop != "disabled"
    cfg.targeted_extraction.max_calls_per_cycle = 0 if stop == "budget" else 1
    extract = Mock(side_effect=AssertionError("guard must stop provider dispatch"))
    runner = CycleRunner(
        cfg=cfg, _targeted_extraction_calls={"model_release_extraction": extract}
    )
    deadline = Mock(can_start=Mock(return_value=False)) if stop == "deadline" else None
    result = runner._replay_targeted_extractions(post_ids={state.pk}, deadline=deadline)
    assert result["calls"] == 0
    extract.assert_not_called()
    assert not EventDossier.objects.filter(
        event_kind_reference__code="product_release"
    ).exists()

"""Offline contract tests; synthetic responses are not model-quality evidence."""


import pytest


def case():
    return {
        "case_id": "pulse-test", "target_brands": ["qwen"],
        "state": {
            "source_text": "Qwen4 weights are available today.", "target_brand": "qwen",
            "tracked_brands": [{"brand_id": "qwen", "aliases": ["Qwen"], "products": [], "accounts": []}],
            "context": {}, "author_affiliations": [],
        },
    }


def extraction():
    return {
        "entities": [{"name": "Qwen4", "source": "post", "evidence": "Qwen4 weights are available today."}],
        "release_findings": {
            "schema": "pulse-release-findings-v1", "findings": [{
                "observed_name": "Qwen4", "version": None, "variant": None,
                "novelty": "new_release", "category": "model-llm",
                "assertions": [{
                    "claim_kind": "availability", "assertion_text": "Qwen4 weights available",
                    "source_excerpt": "Qwen4 weights are available today.", "source_locator": "post",
                    "access_channel": "weights",
                    "effective": {"precision": "unknown", "value": None, "timezone": None},
                }],
            }],
        },
    }


def answers(request, *, positive_keys=None, choices=None):
    result = {}
    for key, question in request["questions"].items():
        if question["type"] == "noul":
            positive = (key in positive_keys if positive_keys is not None else
                        key in {"relevant", "type:releases_updates"} or key.endswith(":concerns:qwen"))
            result[key] = {"type": "noul", "noul": 0.9 if positive else 0.1}
        else:
            selected = "new_release" if key.endswith(":novelty") else "model-llm" if key.endswith(":category") else "none"
            selected = (choices or {}).get(key, selected)
            result[key] = {
                "type": "choice", "choice": selected, "confidence": 1.0,
                "probabilities": {choice: float(choice == selected) for choice in question["criteria"]},
            }
    return {"model": "jev-1.14.0", "answers": result}


def test_two_calls_preserve_existing_axes_and_return_source_bound_release():
    from x_monitor.compressed_classifier import run_case

    calls = []

    def call(provider, request, stage):
        calls.append((provider, stage))
        return extraction() if provider == "ds" else answers(request)

    result = run_case(case(), call, release_channels=("api", "weights"))
    assert calls == [("ds", "extraction"), ("jev", "classification")]
    assert result["contract_valid"], result["contract_errors"]
    publication = result["publication_result"]
    assert publication["by_brand"]["qwen"]["post_types"] == ["releases_updates"]
    assert publication["by_brand"]["qwen"]["sentiment"] == "neutral"
    assert publication["release_findings"][0]["observed_name"] == "Qwen4"
    assert publication["release_findings"][0]["brand_id"] is None
    assert publication["release_findings"][0]["assertions"][0]["access_channel"] == "weights"


@pytest.mark.parametrize("support", [0.1, 0.5, 0.9])
def test_lineage_is_assessed_in_the_same_two_calls_and_requires_affirmative_support(support):
    from x_monitor.compressed_classifier import run_case

    sample = case()
    sample["state"]["source_text"] += " Qwen4 is the successor to Qwen3."
    document = extraction()
    relation = {"relationship_kind": "new_version", "parent_observed_name": "Qwen3",
                "source_locator": "post", "source_excerpt": "Qwen4 is the successor to Qwen3."}
    document["release_findings"]["findings"][0]["lineage_evidence"] = [relation]
    calls = []

    def call(provider, request, stage):
        calls.append((provider, stage))
        if provider == "ds":
            return document
        response = answers(request)
        response["answers"]["release:0:lineage:0:supported"]["noul"] = support
        return response

    result = run_case(sample, call, release_channels=("weights",))
    assert result["contract_valid"], result["contract_errors"]
    assert calls == [("ds", "extraction"), ("jev", "classification")]
    finding = result["publication_result"]["release_findings"][0]
    assert finding["lineage_evidence"] == ([relation] if support > 0.5 else [])
    assert finding["observed_name"] == "Qwen4"


@pytest.mark.parametrize("positive_keys, expected", [
    pytest.param({"target_pitch"}, {"post_types": ["advertising_marketing"]}, id="own-offering-advertising"),
    pytest.param({"target_pitch", "target_incidental_only"}, {"post_types": ["other"]}, id="incidental-advertising-suppressed"),
    *[pytest.param({key, "need_change"}, {"product_labels": ["ideas_requests"]}, id=key)
      for key in ("need_capability", "need_improvement", "need_unmet", "need_idea")],
    pytest.param({"need_idea"}, {"product_labels": []}, id="feedback-needs-desired-change"),
    pytest.param({"positive", "product:testimonial"}, {"sentiment": "positive", "product_labels": ["testimonial"]}, id="positive-testimonial"),
    pytest.param({"positive", "negative", "product:bug", "product:complaint"},
                 {"sentiment": "mixed", "product_labels": ["bug", "complaint"]}, id="mixed-product-experience"),
    pytest.param({"negative", "product:complaint"}, {"sentiment": "negative", "product_labels": ["complaint"]}, id="negative-product-experience"),
])
def test_combined_pair_preserves_positive_legacy_axes(positive_keys, expected):
    from x_monitor.compressed_classifier import run_case

    sample = case()
    sample["state"]["source_text"] = "Qwen product discussion without a release claim."
    calls = []

    def call(provider, request, stage):
        calls.append((provider, stage))
        if provider == "ds":
            return {"entities": [], "release_findings": {"schema": "pulse-release-findings-v1", "findings": []}}
        return answers(request, positive_keys={"relevant", *positive_keys})

    result = run_case(sample, call, release_channels=("api", "weights"))
    assert calls == [("ds", "extraction"), ("jev", "classification")]
    assert result["contract_valid"], result["contract_errors"]
    publication = result["publication_result"]
    assert publication["by_brand"]["qwen"] == {
        "outcome": "classified", "post_types": ["other"],
        "audience_topics": [], "audience_topics_state": "none", "product_labels": [],
        "sentiment": "neutral", "geopolitical_modes": [], "geopolitical_modes_state": "none",
        "china_national_stance": "none", "us_national_stance": "none", **expected,
    }
    assert publication["release_findings"] == ()
    assert publication["untracked_brand_promotions"] == publication["promoted_subjects"] == []


@pytest.mark.parametrize("evaluation, adoption, china, us", [
    ("national_evaluation", True, "pro", "anti"),
    ("origin_evaluation", True, "constructive_critical", "mixed"),
    ("national_evaluation", False, "pro", "anti"),
])
def test_combined_geopolitics_requires_adopted_judgment_for_national_stances(evaluation, adoption, china, us):
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    prepared = build_jev(sample, {"entities": []})
    positives = {"relevant", "geo:reporting", "geo_policy", evaluation}
    if adoption:
        positives.add("national_adoption")
    result = finish(sample, prepared, answers(prepared["request"], positive_keys=positives,
                    choices={"china_national_stance": china, "us_national_stance": us}))
    assert result["contract_valid"], result["contract_errors"]
    brand = result["publication_result"]["by_brand"]["qwen"]
    assert brand["geopolitical_modes"] == ["reporting", "framework", *(["nationalism"] if adoption else [])]
    assert brand["geopolitical_modes_state"] == "selected"
    assert brand["china_national_stance"] == (china if adoption else "none")
    assert brand["us_national_stance"] == (us if adoption else "none")


@pytest.mark.parametrize("identity_question", [None, "identity_namesake_only", "identity_keyword_only", "identity_word_only"])
def test_combined_context_missing_clears_brand_axes(identity_question):
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    prepared = build_jev(sample, {"entities": []})
    # A namesake must override otherwise affirmative brand answers; absent
    # relevance and all post types independently produces context_missing.
    positives = {identity_question, "target_pitch", "positive", "product:testimonial",
                 "topic:agents_tools", "geo_policy", "national_evaluation", "national_adoption"} if identity_question else set()
    result = finish(sample, prepared, answers(prepared["request"], positive_keys=positives,
                    choices={"china_national_stance": "pro", "us_national_stance": "anti"}))
    assert result["contract_valid"], result["contract_errors"]
    assert result["publication_result"]["by_brand"]["qwen"] == {
        "outcome": "context_missing", "post_types": [], "audience_topics": [],
        "audience_topics_state": "unavailable", "product_labels": [], "sentiment": None,
        "geopolitical_modes": [], "geopolitical_modes_state": "unavailable",
        "china_national_stance": None, "us_national_stance": None,
    }


@pytest.mark.parametrize("identity_question", ["identity_namesake_only", "identity_keyword_only", "identity_word_only"])
@pytest.mark.parametrize("identity_probability", [0.499, 0.5, 0.501, 0.9])
def test_identity_vote_does_not_erase_supported_relevant_feed(identity_question, identity_probability):
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:hands_on_usage", "positive"})
    response["answers"][identity_question]["noul"] = identity_probability
    result = finish(sample, prepared, response)
    assert result["publication_result"]["valid"], result["contract_errors"]
    brand = result["publication_result"]["by_brand"]["qwen"]
    assert brand["outcome"] == "classified"
    assert brand["post_types"] == ["hands_on_usage"]
    assert brand["sentiment"] == "positive"


def test_nvidia_gpu_saved_vote_conflict_keeps_supported_labels():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["case_id"] = "2121908611320266918"
    sample["target_brands"] = ["nemo_megatron"]
    sample["state"]["tracked_brands"] = [{"brand_id": "nemo_megatron", "display_name": "NVIDIA", "aliases": ["NVIDIA"], "products": [], "accounts": []}]
    sample["state"]["source_text"] = "EXL3 now works on AMD Strix Halo and Gorgon Halo APUs paired with NVIDIA GPUs."
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:releases_updates"})
    response["answers"]["relevant"]["noul"] = 0.70
    response["answers"]["identity_namesake_only"]["noul"] = 0.71
    result = finish(sample, prepared, response)
    assert result["publication_result"]["valid"]
    assert result["publication_result"]["by_brand"]["nemo_megatron"]["outcome"] == "classified"
    assert result["publication_result"]["identity_votes"]["nemo_megatron"]["relevant"] == 0.70
    assert result["publication_result"]["identity_votes"]["nemo_megatron"]["identity_namesake_only"] == 0.71


@pytest.mark.parametrize("promotion", ["general", "crypto"])
def test_combined_multibrand_labels_keep_one_source_bound_post_promotion(promotion):
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["target_brands"] = ["qwen", "deepseek"]
    sample["state"]["tracked_brands"].append({"brand_id": "deepseek", "aliases": ["DeepSeek"], "products": [], "accounts": []})
    text = "Try Qwen today: it is excellent. DeepSeek crashes for me."
    pitch = "Buy OrbitCoin, our blockchain token!" if promotion == "crypto" else "Try OrbitChat today!"
    name = "OrbitCoin" if promotion == "crypto" else "OrbitChat"
    sample["state"]["source_text"] = text + " " + pitch
    prepared = build_jev(sample, {"entities": [{"name": name, "source": "post", "evidence": pitch}]})
    positives = {"b0:relevant", "b0:target_pitch", "b0:positive",
                 "b1:relevant", "b1:type:hands_on_usage", "b1:product:bug", "b1:negative",
                 "post:untracked_pitch", "binding:S0:pitch"}
    if promotion != "general":
        positives.update({f"post:promotion:{promotion}", f"binding:S0:{promotion}"})
    result = finish(sample, prepared, answers(prepared["request"], positive_keys=positives))
    assert result["contract_valid"], result["contract_errors"]
    publication = result["publication_result"]
    qwen, deepseek = (publication["by_brand"][brand] for brand in ("qwen", "deepseek"))
    assert (qwen["post_types"], qwen["product_labels"], qwen["sentiment"]) == (["advertising_marketing"], [], "positive")
    assert (deepseek["post_types"], deepseek["product_labels"], deepseek["sentiment"]) == (["hands_on_usage"], ["bug"], "negative")
    assert publication["untracked_brand_promotions"] == [promotion]
    assert publication["promoted_subjects"] == [{"name": name, "handle": None, "domain": None,
                                               "account_handle": None, "evidence": sample["state"]["source_text"]}]
    binding, = result["bound_evidence"]
    assert binding["promotion_keys"] == [promotion]
    assert binding["source"] == "post"
    assert sample["state"]["source_text"][binding["start"]:binding["end"]] == binding["evidence"]
    assert all("untracked_brand_promotions" not in brand for brand in (qwen, deepseek))


def test_required_findings_missing_remains_unresolved_after_feed_classification():
    from x_monitor.compressed_classifier import run_case

    calls = []

    def call(provider, request, stage):
        calls.append(provider)
        return {"entities": []} if provider == "ds" else answers(request)

    result = run_case(case(), call, release_channels=("api", "weights"))
    assert not result["contract_valid"]
    assert "invalid_release_findings" in result["contract_errors"]
    assert calls == ["ds", "jev"]
    assert result["publication_result"]["release_unresolved"] is True


def test_umbrella_names_are_visible_in_actual_questions_without_catalog_in_extraction():
    from x_monitor.compressed_classifier import build_jev, make_extraction_request

    sample = case()
    sample["target_brands"] = ["llama"]
    sample["state"].update(target_brand="llama", source_text="Meta releases XYZ.", tracked_brands=[
        {"brand_id": "llama", "aliases": ["Meta"], "products": [], "accounts": []},
    ])
    request = make_extraction_request(sample)
    assert "llama" not in request["messages"][1]["content"]
    prepared = build_jev(sample, {"entities": []})
    assert prepared["request"]["state"]["target_umbrella_post_matched_names"] == {"llama": ["Meta"]}
    assert "Meta" in prepared["request"]["questions"]["type:releases_updates"]["instructions"]


@pytest.mark.parametrize("mutation", [
    lambda response: response.update(model="jev-latest"),
    lambda response: response["answers"].pop("relevant"),
    lambda response: response["answers"]["relevant"].update(noul=True),
    lambda response: response["answers"].update(extra={"type": "noul", "noul": 0.9}),
])
def test_bad_jev_response_cannot_publish_partial_classification(mutation):
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"])
    mutation(response)
    assert not finish(sample, prepared, response)["contract_valid"]


def test_release_update_type_applies_only_to_supported_brand_and_keeps_unknown_owner():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["target_brands"] = ["qwen", "deepseek"]
    sample["state"]["tracked_brands"].append({"brand_id": "deepseek", "aliases": ["DeepSeek"], "products": [], "accounts": []})
    prepared = build_jev(sample, extraction(), release_channels=("api", "weights"))
    response = answers(prepared["request"])
    # Neither ordinary per-brand release question caught it; the release-specific
    # finding concerns Qwen only, so its tag must not transfer to DeepSeek.
    for key in response["answers"]:
        if key.endswith("type:releases_updates"):
            response["answers"][key]["noul"] = 0.1
        elif key.endswith(":relevant"):
            response["answers"][key]["noul"] = 0.9
    result = finish(sample, prepared, response)
    assert result["contract_valid"], result["contract_errors"]
    assert "releases_updates" in result["publication_result"]["by_brand"]["qwen"]["post_types"]
    assert "releases_updates" not in result["publication_result"]["by_brand"]["deepseek"]["post_types"]
    assert result["publication_result"]["release_findings"][0]["brand_id"] is None


def test_unattributed_release_gets_post_type_without_a_tracked_brand_connection():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["target_brands"] = ["_unattributed"]
    sample["state"].update(target_brand="_unattributed", tracked_brands=[])
    prepared = build_jev(sample, extraction(), release_channels=("api", "weights"))
    response = answers(prepared["request"])
    for value in response["answers"].values():
        if value["type"] == "noul":
            value["noul"] = 0.1
    result = finish(sample, prepared, response)
    assert result["contract_valid"], result["contract_errors"]
    assert result["publication_result"]["by_brand"]["_unattributed"]["post_types"] == ["releases_updates"]


@pytest.mark.parametrize("support", [0.1, 0.5, 0.6, 0.9])
def test_issuer_verification_stays_in_the_pair_and_never_assigns_canonical_owner(support):
    from x_monitor.compressed_classifier import run_case

    sample = case()
    text = "We release Qwen4 weights today."
    sample["state"]["source_text"] = text
    document = extraction()
    document["entities"][0]["evidence"] = text
    finding = document["release_findings"]["findings"][0]
    finding["assertions"][0].update(source_excerpt=text, assertion_text="Qwen4 weights released")
    finding["issuer_evidence"] = {"relation": "source_author", "source_locator": "post",
                                  "source_excerpt": text, "observed_name": None}
    calls = []

    def call(provider, request, stage):
        calls.append(provider)
        if provider == "ds":
            return document
        response = answers(request)
        response["answers"]["release:0:issuer_supported"]["noul"] = support
        return response

    result = run_case(sample, call, release_channels=("api", "weights"))
    assert result["contract_valid"], result["contract_errors"]
    saved = result["publication_result"]["release_findings"][0]
    assert (saved["issuer_evidence"] is not None) == (support > 0.5)
    assert saved["brand_id"] is None
    assert calls == ["ds", "jev"]
    assert result["publication_result"]["release_findings"][0]["brand_id"] is None


def test_publisher_is_saved_only_when_issuer_and_tracked_brand_are_supported():
    from x_monitor.compressed_classifier import run_case

    document = extraction()
    document['release_findings']['findings'][0]['issuer_evidence'] = {
        'relation': 'attributed_party', 'source_locator': 'post',
        'source_excerpt': 'Qwen4 weights are available today.', 'observed_name': 'Qwen',
    }

    def run(*, issuer, publisher):
        def call(provider, request, stage):
            if provider == 'ds':
                return document
            result = answers(request)
            result['answers']['release:0:issuer_supported']['noul'] = 0.9 if issuer else 0.1
            result['answers']['release:0:publisher:qwen']['noul'] = 0.9 if publisher else 0.1
            return result
        return run_case(case(), call, release_channels=('api', 'weights'))['publication_result']['release_findings'][0]

    assert run(issuer=True, publisher=True)['brand_id'] == 'qwen'
    assert run(issuer=True, publisher=False)['brand_id'] is None
    assert run(issuer=False, publisher=True)['brand_id'] is None


def test_family_evidence_requires_source_support_and_jev_confirmation():
    from x_monitor.compressed_classifier import run_case

    document = extraction()
    document['release_findings']['findings'][0]['family_evidence'] = {
        'name': 'Qwen', 'source_locator': 'post', 'source_excerpt': 'Qwen4 weights are available today.',
    }

    def run(supported):
        def call(provider, request, stage):
            if provider == 'ds':
                return document
            result = answers(request)
            result['answers']['release:0:family_supported']['noul'] = 0.9 if supported else 0.1
            return result
        return run_case(case(), call, release_channels=('api', 'weights'))['publication_result']['release_findings'][0]

    assert run(True)['family_evidence']['name'] == 'Qwen'
    assert run(False)['family_evidence'] is None


def test_suite_question_and_category_distinguish_launches_from_components():
    from x_monitor.compressed_classifier import build_jev

    prepared = build_jev(case(), extraction(), release_channels=('api', 'weights'))
    novelty = prepared['request']['questions']['release:0:novelty']['criteria']['new_release']
    categories = prepared['request']['questions']['release:0:category']['criteria']
    assert 'existing component' in novelty and 'explicitly introduced' in novelty
    assert 'application feature' in categories['model-other']
    assert 'application features' in categories['other']


def test_invalid_release_data_does_not_prevent_independent_feed_answers():
    from x_monitor.compressed_classifier import run_case

    calls = []

    def call(provider, request, stage):
        calls.append(provider)
        return {"entities": []} if provider == "ds" else answers(request)

    result = run_case(case(), call, release_channels=("api", "weights"))
    assert calls == ["ds", "jev"]
    assert result["publication_result"]["valid"] is True
    assert result["publication_result"]["release_unresolved"] is True
    assert "release_findings" not in result["publication_result"]
    assert result["publication_result"]["by_brand"]["qwen"]["outcome"] == "classified"


def test_completed_post_is_published_before_slow_sibling_finishes(monkeypatch):
    import threading
    from types import SimpleNamespace
    from x_monitor import compressed_classifier as classifier

    released = threading.Event()
    published = threading.Event()
    original = classifier._run_prepared_case

    def run(sample, request, call, *, release_channels):
        if sample["case_id"] == "slow":
            assert released.wait(5)
        return original(sample, request, call, release_channels=release_channels)

    monkeypatch.setattr(classifier, "_run_prepared_case", run)
    class Client:
        release_channels = ("api", "weights")
        request_identity = "fixture"
        def messages_create(self, **kwargs):
            import json
            if kwargs["model"].startswith("deepseek"):
                return extraction()
            return answers(json.loads(kwargs["messages"][0]["content"]))

    tweets = [
        {"tweet_id": value, "text": case()["state"]["source_text"], "brand_ids": ["qwen"], "context": []}
        for value in ("slow", "fast")
    ]

    def on_result(tweet, result):
        if tweet["tweet_id"] == "fast":
            assert result["valid"]
            published.set()
            released.set()

    results = classifier.classify_batch(
        tweets, [SimpleNamespace(brand_id="qwen", display_name="Qwen", is_sentinel=False)],
        Client(), max_tokens=4096, max_workers=2, on_result=on_result,
    )
    assert published.is_set()
    assert all(result["valid"] for result in results)


def test_selected_production_configuration_runs_six_posts_concurrently(monkeypatch):
    import threading
    from pathlib import Path
    from types import SimpleNamespace
    from x_monitor import compressed_classifier as classifier
    from x_monitor.config import load_config

    cfg = load_config(Path("config.yaml")).harvest.enrichment
    assert cfg.pulse_classification_concurrency == 6
    gate = threading.Barrier(cfg.pulse_classification_concurrency, timeout=5)
    original = classifier._run_prepared_case

    def synchronized(sample, request, call, *, release_channels):
        gate.wait()
        return original(sample, request, call, release_channels=release_channels)

    monkeypatch.setattr(classifier, "_run_prepared_case", synchronized)
    class Client:
        release_channels = ("api", "weights")
        request_identity = "fixture"
        def messages_create(self, **kwargs):
            import json
            if kwargs["model"].startswith("deepseek"):
                return extraction()
            return answers(json.loads(kwargs["messages"][0]["content"]))

    tweets = [
        {"tweet_id": str(index), "text": case()["state"]["source_text"], "brand_ids": ["qwen"], "context": []}
        for index in range(cfg.pulse_classification_concurrency)
    ]
    results = classifier.classify_batch(
        tweets, [SimpleNamespace(brand_id="qwen", display_name="Qwen", is_sentinel=False)],
        Client(), max_tokens=4096, max_workers=cfg.pulse_classification_concurrency,
    )
    assert all(result["valid"] for result in results)


def test_uncertain_promotion_does_not_discard_valid_sentiment_and_post_type():
    from x_monitor.compressed_classifier import run_case

    def call(provider, request, stage):
        if provider == 'ds':
            return extraction()
        response = answers(request)
        response['answers']['binding:missing_subject']['noul'] = 0.9
        return response

    result = run_case(case(), call, release_channels=('api', 'weights'))
    assert result['publication_result']['valid'] is True
    assert result['publication_result']['promotion_unresolved'] is True
    assert result['publication_result']['by_brand']['qwen']['sentiment'] == 'neutral'
    assert 'releases_updates' in result['publication_result']['by_brand']['qwen']['post_types']


def test_missing_promotion_answer_preserves_valid_feed_and_release_decisions():
    from x_monitor.compressed_classifier import run_case

    def call(provider, request, stage):
        if provider == 'ds':
            return extraction()
        response = answers(request)
        response['answers'].pop('binding:missing_subject')
        return response

    result = run_case(case(), call, release_channels=('api', 'weights'))
    assert result['publication_result']['valid'] is True
    assert result['publication_result']['promotion_unresolved'] is True
    assert result['publication_result'].get('release_unresolved') is not True
    assert result['publication_result']['release_independent_valid'] is True
    assert result['publication_result']['by_brand']['qwen']['sentiment'] == 'neutral'


def test_missing_sentiment_answer_is_not_treated_as_promotion_uncertainty():
    from x_monitor.compressed_classifier import run_case

    def call(provider, request, stage):
        if provider == 'ds':
            return extraction()
        response = answers(request)
        response['answers'].pop('positive')
        response['answers'].pop('binding:missing_subject')
        return response

    result = run_case(case(), call, release_channels=('api', 'weights'))
    assert result['publication_result']['valid'] is False
    assert result['publication_result'].get('promotion_unresolved') is not True


def test_missing_subject_binding_answer_keeps_independent_feed_axes():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample['state']['source_text'] = 'Qwen4 is useful. Try OrbitChat today!'
    prepared = build_jev(sample, {'entities': [
        {'name': 'OrbitChat', 'source': 'post', 'evidence': 'Try OrbitChat today!'},
    ]})
    response = answers(prepared['request'])
    response['answers'].pop('binding:S0:pitch')
    result = finish(sample, prepared, response)
    assert result['publication_result']['valid'] is True
    assert result['publication_result']['promotion_unresolved'] is True
    assert result['publication_result']['by_brand']['qwen']['sentiment'] == 'neutral'


def test_release_and_promotion_can_both_remain_unresolved_with_valid_feed():
    from x_monitor.compressed_classifier import run_case

    def call(provider, request, stage):
        if provider == 'ds':
            document = extraction()
            document['release_findings'] = {'schema': 'invalid', 'findings': []}
            return document
        response = answers(request)
        response['answers'].pop('binding:missing_subject')
        return response

    result = run_case(case(), call, release_channels=('api', 'weights'))
    publication = result['publication_result']
    assert publication['valid'] is True
    assert publication['release_unresolved'] is True
    assert publication['promotion_unresolved'] is True
    assert 'release_findings' not in publication
    assert publication['by_brand']['qwen']['sentiment'] == 'neutral'


@pytest.mark.parametrize(("source", "expected"), [
    ("用的都是qwen", ["Qwen"]),
    ("Meta的AI助手Muse", ["Meta", "Muse"]),
    ("Meta와Qwen은좋다", ["Meta", "Qwen"]),
    ("notMeta, Metaverse, MiMoé, Museology, qwenish", []),
])
def test_untranslated_source_preserves_real_catalog_names_in_jev_request(source, expected):
    from x_monitor.compressed_classifier import run_case

    sample = case()
    sample["state"].update(source_text=source, source_language="zh", english_translation="")
    sample["state"]["tracked_brands"][0]["aliases"] = ["Meta", "Muse", "MiMo", "Qwen"]
    stages = []

    def call(provider, request, stage):
        stages.append(stage)
        if provider == "ds":
            return {"entities": [], "release_findings": {"schema": "pulse-release-findings-v1", "findings": []}}
        assert request["state"]["target_umbrella_post_matched_names"]["qwen"] == expected
        return answers(request, positive_keys=set())

    published = run_case(sample, call, release_channels=("weights",))["publication_result"]
    assert stages == ["extraction", "classification"]
    assert published["by_brand"]["qwen"]["outcome"] == "context_missing"
    assert published["by_brand"]["qwen"]["sentiment"] is None


def test_original_product_candidates_and_brand_terms_agree_in_real_classifier_batch():
    from types import SimpleNamespace
    import json
    from x_monitor.compressed_classifier import classify_batch

    class Client:
        release_channels = ("weights",)
        def messages_create(self, **kwargs):
            if kwargs["model"].startswith("deepseek"):
                return {"entities": [], "release_findings": {"schema": "pulse-release-findings-v1", "findings": []}}
            request = json.loads(kwargs["messages"][0]["content"])
            state = request["state"]
            assert state["target_model_candidates"] == ["RealModel", "海螺", "混元"]
            assert state["target_umbrella_post_matched_names"]["qwen"] == ["RealModel", "海螺", "混元"]
            return answers(request, positive_keys=set())

    results = classify_batch([{"tweet_id": "source-match", "brand_ids": ["qwen"],
                               "text": "qwenish Museology MiMoé 我用RealModel和海螺了 AI", "source_language": "zh",
                               "context": [{"provenance": "stored_quote", "text": "再试混元"}],
                               "english_translation": "Muse, an AI product",
                               "tracked_brand_catalog": [{"brand_id": "qwen", "aliases": ["Qwen"],
                                                           "products": ["MiMo", "Muse", "RealModel", "海螺", "混元", "AI", "我"]}]}],
                             [SimpleNamespace(brand_id="qwen", display_name="Qwen", is_sentinel=False)],
                             Client(), max_tokens=4096)
    assert results[0]["valid"] and results[0]["by_brand"]["qwen"]["outcome"] == "context_missing"


def test_catalog_display_name_is_authoritative_even_when_post_mentions_only_a_product():
    from x_monitor.attribution import _tracked_brand_catalog, _validated_tracked_brand_catalog_snapshot
    from x_monitor.compressed_classifier import build_jev
    sample = case()
    sample["target_brands"] = ["llama"]
    historical = {"brand_id": "llama", "aliases": ["Llama", "Meta"], "products": ["Muse"], "accounts": []}
    def snapshot(entry):
        return _tracked_brand_catalog([], [{"tracked_brand_catalog": [entry]}])
    old = snapshot(historical)
    current = snapshot({**historical, "display_name": "Meta"})
    assert _validated_tracked_brand_catalog_snapshot(old) == old
    assert _validated_tracked_brand_catalog_snapshot(current) == current
    assert old["revision"] != current["revision"]
    sample["state"].update(target_brand="llama", source_text="I like Muse.", tracked_brands=current["brands"])
    request = build_jev(sample, {"entities": []})["request"]
    assert "Meta and its offerings" in request["questions"]["positive"]["instructions"]
    assert request["state"]["target_umbrella_post_matched_names"]["llama"] == ["Muse"]


@pytest.mark.parametrize("brands", [["qwen", "deepseek"], ["deepseek", "qwen"]])
def test_disputed_release_attribution_preserves_complete_sibling_judgment(brands):
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["target_brands"] = brands
    sample["state"]["tracked_brands"].append(
        {"brand_id": "deepseek", "aliases": ["DeepSeek"], "products": [], "accounts": []}
    )
    prepared = build_jev(sample, extraction(), release_channels=("weights",))
    mapping = prepared["metadata"]["question_map"]
    positive = {
        mapping["qwen"]["identity_namesake_only"],
        mapping["deepseek"]["relevant"],
        mapping["deepseek"]["type:hands_on_usage"],
        mapping["deepseek"]["negative"],
        mapping["deepseek"]["product:bug"],
        "release:0:concerns:qwen",
    }
    result = finish(sample, prepared, answers(prepared["request"], positive_keys=positive))
    assert result["contract_valid"], result["contract_errors"]
    publication = result["publication_result"]
    assert set(publication["by_brand"]) == set(brands)
    assert publication["by_brand"]["qwen"]["outcome"] == "context_missing"
    sibling = publication["by_brand"]["deepseek"]
    assert sibling["sentiment"] == "negative"
    assert sibling["post_types"] == ["hands_on_usage"]
    assert sibling["product_labels"] == ["bug"]
    assert publication["release_findings"][0]["observed_name"] == "Qwen4"
    assert publication["release_findings"][0]["brand_id"] is None


def test_release_questions_overflow_keeps_feed_and_marks_release_unresolved():
    from x_monitor.compressed_classifier import build_jev, run_case

    sample = case()
    brands = ["qwen"] + [f"brand{i}" for i in range(16)]
    sample["target_brands"] = brands
    sample["state"]["tracked_brands"] = [
        {"brand_id": b, "aliases": [b], "products": [], "accounts": []} for b in brands
    ]
    combined = build_jev(sample, extraction(), release_channels=("weights",))
    feed = build_jev(sample, extraction(), release_channels=None)
    assert not combined["metadata"]["context_valid"]
    assert feed["metadata"]["context_valid"]
    calls = []

    def call(provider, request, stage):
        calls.append((provider, stage))
        return extraction() if provider == "ds" else answers(request)

    result = run_case(sample, call, release_channels=("weights",))
    assert calls == [("ds", "extraction"), ("jev", "classification")]
    assert result["publication_result"]["valid"]
    assert set(result["publication_result"]["by_brand"]) == set(brands)
    assert result["publication_result"]["release_unresolved"]
    assert not result["publication_result"].get("release_independent_valid")


def test_feed_itself_overflows_but_release_fits_and_is_saved_independently():
    from x_monitor.compressed_classifier import build_jev, run_case

    sample = case()
    brands = ["qwen"] + [f"brand{i}" for i in range(17)]
    sample["target_brands"] = brands
    sample["state"]["tracked_brands"] = [
        {"brand_id": b, "aliases": [b], "products": [], "accounts": []} for b in brands
    ]
    assert not build_jev(sample, extraction(), release_channels=None)["metadata"]["context_valid"]
    calls = []

    def call(provider, request, stage):
        calls.append((provider, stage))
        return extraction() if provider == "ds" else answers(request)

    result = run_case(sample, call, release_channels=("weights",))
    assert calls == [("ds", "extraction"), ("jev", "classification")]
    assert not result["publication_result"]["valid"]
    assert result["publication_result"]["release_independent_valid"]
    assert result["publication_result"]["release_findings"][0]["observed_name"] == "Qwen4"


def test_oversized_source_that_cannot_fit_either_request_sends_no_jev_call():
    from x_monitor.compressed_classifier import run_case

    sample = case()
    sample["state"]["source_text"] = "large " * 30000
    document = extraction()
    document["entities"] = []
    document["release_findings"]["findings"] = []
    calls = []

    def call(provider, request, stage):
        calls.append((provider, stage))
        return document

    result = run_case(sample, call, release_channels=("weights",))
    assert calls == [("ds", "extraction")]
    assert not result["publication_result"]["valid"]
    assert result["publication_result"]["release_independent_valid"]
    assert result["publication_result"]["release_findings"] == ()


def test_release_only_response_cannot_supply_unasked_feed_answers():
    from x_monitor.compressed_classifier import build_jev, run_case

    sample = case()
    brands = ["qwen"] + [f"brand{i}" for i in range(17)]
    sample["target_brands"] = brands
    sample["state"]["tracked_brands"] = [
        {"brand_id": b, "aliases": [b], "products": [], "accounts": []} for b in brands
    ]
    full_request = build_jev(sample, extraction(), release_channels=("weights",))["request"]

    def call(provider, request, stage):
        if provider == "ds":
            return extraction()
        assert all(key.startswith("release:") for key in request["questions"])
        return answers(full_request)

    result = run_case(sample, call, release_channels=("weights",))
    assert not result["publication_result"]["valid"]
    assert not result["publication_result"]["by_brand"]
    assert "unexpected_jev_answers" in result["contract_errors"]


def test_feed_overflow_preserves_valid_empty_release_decision():
    from x_monitor.compressed_classifier import run_case

    sample = case()
    brands = ["qwen"] + [f"brand{i}" for i in range(17)]
    sample["target_brands"] = brands
    sample["state"]["tracked_brands"] = [
        {"brand_id": b, "aliases": [b], "products": [], "accounts": []} for b in brands
    ]
    document = extraction()
    document["release_findings"]["findings"] = []
    calls = []

    def call(provider, request, stage):
        calls.append((provider, stage))
        return document if provider == "ds" else answers(request)

    result = run_case(sample, call, release_channels=("weights",))
    assert calls == [("ds", "extraction")]
    assert not result["publication_result"]["valid"]
    assert result["publication_result"]["release_independent_valid"]
    assert result["publication_result"]["release_findings"] == ()


def test_oversized_source_with_nonempty_release_sends_no_oversized_jev_request():
    from x_monitor.compressed_classifier import run_case

    sample = case()
    sample["state"]["source_text"] += " large" * 30000
    calls = []

    def call(provider, request, stage):
        calls.append((provider, stage))
        return extraction()

    result = run_case(sample, call, release_channels=("weights",))
    assert calls == [("ds", "extraction")]
    assert not result["publication_result"]["valid"]
    assert not result["publication_result"].get("release_independent_valid")
    assert "jev_context_overflow" in result["contract_errors"]


@pytest.mark.parametrize("question", ["identity_namesake_only", "identity_keyword_only", "identity_word_only"])
@pytest.mark.parametrize("probability,expected", [(0.499, "classified"), (0.5, "context_missing"), (0.501, "context_missing")])
def test_identity_veto_requires_unsupported_relevance_and_inclusive_boundary(question, probability, expected):
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["case_id"] = "2121100720535691663"
    sample["target_brands"] = ["llama"]
    sample["state"]["tracked_brands"] = [{"brand_id": "llama", "display_name": "Meta", "aliases": ["Meta"], "products": [], "accounts": []}]
    sample["state"]["source_text"] = "We launched the official Meta Box Agent Skill and Coding with AI guide."
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"type:hands_on_usage", "positive"})
    response["answers"][question]["noul"] = probability
    result = finish(sample, prepared, response)
    assert result["publication_result"]["valid"], result["contract_errors"]
    brand = result["publication_result"]["by_brand"]["llama"]
    assert brand["outcome"] == expected
    if expected == "context_missing":
        assert brand["sentiment"] is None
        assert brand["post_types"] == []


def test_sglang_named_announcement_is_preserved():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["case_id"] = "2120944999416377762"
    sample["target_brands"] = ["sglang"]
    sample["state"].update(source_text="Announcing SGLang v1.0 at SGLang Summit: high-performance inference for LLMs.",
                           tracked_brands=[{"brand_id": "sglang", "aliases": ["SGLang"], "products": [], "accounts": []}])
    prepared = build_jev(sample, {"entities": []})
    result = finish(sample, prepared, answers(prepared["request"], positive_keys={"relevant", "type:releases_updates"}))
    assert result["publication_result"]["by_brand"]["sglang"]["post_types"] == ["releases_updates"]


def test_other_offerings_quoted_praise_remains_neutral_for_relevant_target():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["state"]["source_text"] = 'Qwen is mentioned. The author quotes "DeepSeek is wonderful".'
    prepared = build_jev(sample, {"entities": []})
    result = finish(sample, prepared, answers(prepared["request"], positive_keys={"relevant", "positive", "evaluation_elsewhere"}))
    assert result["publication_result"]["by_brand"]["qwen"]["sentiment"] == "neutral"


def test_multibrand_namesake_cannot_clear_sibling_or_transfer_praise():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["target_brands"] = ["qwen", "llama"]
    sample["state"]["source_text"] = "Qwen works well. The band Muse released an album."
    sample["state"]["tracked_brands"].append({"brand_id": "llama", "aliases": ["Muse"], "products": [], "accounts": []})
    prepared = build_jev(sample, {"entities": []})
    positive = {"b0:relevant", "b0:type:hands_on_usage", "b0:positive", "b1:identity_namesake_only"}
    result = finish(sample, prepared, answers(prepared["request"], positive_keys=positive))
    assert result["publication_result"]["valid"]
    by_brand = result["publication_result"]["by_brand"]
    assert by_brand["qwen"]["sentiment"] == "positive"
    assert by_brand["llama"]["outcome"] == "context_missing"
    assert by_brand["llama"]["post_types"] == []


def test_unattributed_discovery_identity_handling_is_unchanged():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["target_brands"] = ["_unattributed"]
    sample["state"]["tracked_brands"] = [{"brand_id": "_unattributed", "aliases": [], "products": [], "accounts": []}]
    prepared = build_jev(sample, {"entities": []})
    result = finish(sample, prepared, answers(prepared["request"], positive_keys={"relevant", "positive", "identity_namesake_only"}))
    assert result["publication_result"]["by_brand"]["_unattributed"]["outcome"] == "context_missing"


def test_identity_rule_has_new_merge_revision_and_retains_previous_read_compatibility():
    from core.classification_contract import COMPRESSED_CLASSIFIER_REVISIONS, COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS

    previous = ("compressed8-pulse-content-v2", "compressed8-pulse-brand-v2", "compressed8-pulse-merge-v2")
    assert previous in COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS
    assert COMPRESSED_CLASSIFIER_REVISIONS[:2] == previous[:2]
    assert COMPRESSED_CLASSIFIER_REVISIONS[2] != previous[2]


def test_llama_cpp_namesake_does_not_become_a_meta_label_on_conflicting_vote():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["case_id"] = "2122009219880894721"
    sample["target_brands"] = ["llama"]
    sample["state"].update(
        source_text="We released Hibana, an inference engine, faster than vLLM, NVIDIA Flare, llama.cpp and TensorFold.",
        tracked_brands=[{"brand_id": "llama", "display_name": "Meta", "aliases": ["Meta", "Llama"], "products": [], "accounts": []}],
    )
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:releases_updates", "identity_namesake_only"})
    result = finish(sample, prepared, response)
    assert result["publication_result"]["valid"]
    assert result["publication_result"]["by_brand"]["llama"]["outcome"] == "context_missing"


@pytest.mark.parametrize("text,aliases", [
    ("Meta reports that Llama works with llama.cpp.", ["Meta", "Llama"]),
    ("The Meta.ai service is now available.", ["Meta", "Meta.ai"]),
])
def test_supported_context_is_not_rejected_as_qualified_namesake(text, aliases):
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["target_brands"] = ["llama"]
    sample["state"].update(source_text=text, tracked_brands=[{"brand_id": "llama", "display_name": "Meta", "aliases": aliases, "products": [], "accounts": []}])
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:hands_on_usage", "identity_namesake_only"})
    result = finish(sample, prepared, response)
    assert result["publication_result"]["valid"]
    assert result["publication_result"]["by_brand"]["llama"]["outcome"] == "classified"


def test_identity_conflict_without_independent_target_support_stays_unresolved():
    from x_monitor.compressed_classifier import build_jev, finish
    sample = case()
    sample["target_brands"] = ["llama"]
    sample["state"].update(source_text="The team reported new results.", tracked_brands=[{
        "brand_id": "llama", "display_name": "Meta", "aliases": ["Meta", "Llama"], "products": [], "accounts": [],
    }])
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:hands_on_usage", "identity_namesake_only"})
    result = finish(sample, prepared, response)
    assert result["publication_result"]["by_brand"]["llama"]["outcome"] == "context_missing"


def test_official_domain_is_valid_target_evidence_despite_conflicting_identity_vote():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["target_brands"] = ["nemo_megatron"]
    sample["state"].update(source_text="NVIDIA.com published our latest GPU developer update.", tracked_brands=[{
        "brand_id": "nemo_megatron", "display_name": "NVIDIA", "aliases": ["NVIDIA"],
        "domains": ["nvidia.com"], "products": [], "accounts": [],
    }])
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:releases_updates", "identity_namesake_only"})
    result = finish(sample, prepared, response)
    assert result["publication_result"]["by_brand"]["nemo_megatron"]["outcome"] == "classified"


@pytest.mark.parametrize("identity_question", ["identity_word_only", "identity_namesake_only", "identity_keyword_only"])
def test_generic_meta_word_does_not_validate_llama_cpp_as_meta(identity_question):
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["target_brands"] = ["llama"]
    sample["state"].update(source_text="We make a meta comparison of the independent llama.cpp project.", tracked_brands=[{
        "brand_id": "llama", "display_name": "Meta", "aliases": ["Meta", "meta", "Llama"], "products": [], "accounts": [],
    }])
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:results_analysis", identity_question})
    result = finish(sample, prepared, response)
    assert result["publication_result"]["by_brand"]["llama"]["outcome"] == "context_missing"


@pytest.mark.parametrize("text", [
    "Independent software details: https://evil.example/nvidia.com",
    "Independent software details: https://nvidia.com.evil.example/product",
])
def test_official_domain_in_unrelated_url_does_not_validate_identity(text):
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["target_brands"] = ["nemo_megatron"]
    sample["state"].update(source_text=text, tracked_brands=[{
        "brand_id": "nemo_megatron", "display_name": "NVIDIA", "aliases": ["NVIDIA"],
        "domains": ["nvidia.com"], "products": [], "accounts": [],
    }])
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:releases_updates", "identity_namesake_only"})
    result = finish(sample, prepared, response)
    assert result["publication_result"]["by_brand"]["nemo_megatron"]["outcome"] == "context_missing"


@pytest.mark.parametrize("text", ["meta released new support for llama.cpp.", "meta is integrating llama.cpp into its products."])
def test_lowercase_brand_with_explicit_release_is_not_erased_as_generic_word(text):
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["target_brands"] = ["llama"]
    sample["state"].update(source_text=text, tracked_brands=[{
        "brand_id": "llama", "display_name": "Meta", "aliases": ["Meta", "meta", "Llama"], "products": [], "accounts": [],
    }])
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:releases_updates", "identity_word_only"})
    result = finish(sample, prepared, response)
    assert result["publication_result"]["by_brand"]["llama"]["outcome"] == "classified"


def test_meta_box_compound_namesake_stays_unresolved_when_votes_conflict():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["case_id"] = "2121100720535691663"
    sample["target_brands"] = ["llama"]
    sample["state"].update(source_text="We just launched the official Meta Box Agent Skill and Coding with AI guide.", tracked_brands=[{
        "brand_id": "llama", "display_name": "Meta", "aliases": ["Meta", "Llama", "Meta Llama"], "products": [], "accounts": [],
    }])
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:releases_updates", "identity_namesake_only"})
    result = finish(sample, prepared, response)
    assert result["publication_result"]["by_brand"]["llama"]["outcome"] == "context_missing"


def test_known_compound_product_still_supports_brand_on_conflicting_vote():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["target_brands"] = ["llama"]
    sample["state"].update(source_text="Meta Llama weights are available.", tracked_brands=[{
        "brand_id": "llama", "display_name": "Meta", "aliases": ["Meta", "Llama", "Meta Llama"], "products": [], "accounts": [],
    }])
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:releases_updates", "identity_namesake_only"})
    result = finish(sample, prepared, response)
    assert result["publication_result"]["by_brand"]["llama"]["outcome"] == "classified"


@pytest.mark.parametrize("brand,name,text", [
    ("llama", "Meta", "Meta Announces New AI Research."),
    ("llama", "Meta", "Meta New AI Model Released."),
    ("nemo_megatron", "NVIDIA", "NVIDIA Releases New GPUs."),
])
def test_title_case_brand_headline_with_conflicting_votes_keeps_supported_labels(brand, name, text):
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["target_brands"] = [brand]
    sample["state"].update(source_text=text, tracked_brands=[{
        "brand_id": brand, "display_name": name, "aliases": [name], "products": [], "accounts": [],
    }])
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:releases_updates", "identity_namesake_only"})
    result = finish(sample, prepared, response)
    assert result["publication_result"]["by_brand"][brand]["outcome"] == "classified"


def test_maya_release_nvidia_passing_mention_is_other_neutral():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["case_id"] = "2121908611320266918"
    sample["target_brands"] = ["nemo_megatron"]
    sample["state"].update(source_text=(
        "Maya v1.1.64 is out 💫\n\n"
        "EXL3 now works on AMD Strix Halo and Gorgon Halo APUs paired with NVIDIA GPUs, just like GGUF since v1.1.62.\n\n"
        "GLM-5.3-Flash EXL3 can now run across both GPUs, sharing one model. Maya automatically keeps each part on the GPU where it's faster.\n\n"
        "Also in this release:\n- Multi-GPU DeepSeek decoding is back to pre-v1.1.58 speeds (#956).\n"
        "- Qwen GGUFs with mixed expert formats now work.\n- Damaged MiniMax files are now detected."
    ), tracked_brands=[{"brand_id": "nemo_megatron", "display_name": "NVIDIA", "aliases": ["NVIDIA"], "products": [], "accounts": []}])
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:releases_updates", "positive", "identity_namesake_only"})
    response["answers"]["relevant"]["noul"] = 0.70
    response["answers"]["identity_namesake_only"]["noul"] = 0.71
    result = finish(sample, prepared, response)
    brand = result["publication_result"]["by_brand"]["nemo_megatron"]
    assert brand["outcome"] == "classified"
    assert brand["post_types"] == ["other"]
    assert brand["sentiment"] == "neutral"
    assert result["publication_result"]["identity_votes"]["nemo_megatron"]["identity_namesake_only"] == 0.71


@pytest.mark.parametrize("brand,name", [("deepseek", "DeepSeek"), ("qwen", "Qwen"), ("minimax", "MiniMax")])
def test_maya_release_does_not_transfer_launch_or_praise_to_other_brands(brand, name):
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["case_id"] = "2121908611320266918"
    sample["target_brands"] = [brand]
    sample["state"].update(source_text=(
        "Maya v1.1.64 is out 💫\n\n"
        "EXL3 now works on AMD Strix Halo and Gorgon Halo APUs paired with NVIDIA GPUs.\n\n"
        "Also in this release:\n- Multi-GPU DeepSeek decoding is back to pre-v1.1.58 speeds (#956).\n"
        "- Qwen GGUFs with mixed expert formats now work.\n- Damaged MiniMax files are now detected."
    ), tracked_brands=[{"brand_id": brand, "display_name": name, "aliases": [name], "products": [], "accounts": []}])
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:releases_updates", "positive", "identity_namesake_only"})
    result = finish(sample, prepared, response)
    judgment = result["publication_result"]["by_brand"][brand]
    assert judgment["outcome"] == "classified"
    assert "releases_updates" not in judgment["post_types"]
    assert judgment["sentiment"] == "neutral"


def test_release_note_with_target_specific_launch_and_praise_keeps_its_labels():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["state"]["source_text"] = "Maya is out.\nAlso in this release:\n- Qwen releases an excellent new model."
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:releases_updates", "positive", "identity_namesake_only"})
    judgment = finish(sample, prepared, response)["publication_result"]["by_brand"]["qwen"]
    assert judgment["post_types"] == ["releases_updates"]
    assert judgment["sentiment"] == "positive"


def test_release_note_with_target_specific_praise_does_not_inherit_launch():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["state"]["source_text"] = "Maya is out.\nAlso in this release:\n- Qwen works really well."
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "type:releases_updates", "positive", "identity_namesake_only"})
    judgment = finish(sample, prepared, response)["publication_result"]["by_brand"]["qwen"]
    assert judgment["post_types"] == ["other"]
    assert judgment["sentiment"] == "positive"


def test_maya_multibrand_conflicts_do_not_share_launch_or_praise():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["case_id"] = "2121908611320266918"
    names = [("nemo_megatron", "NVIDIA"), ("deepseek", "DeepSeek"), ("qwen", "Qwen"), ("minimax", "MiniMax")]
    sample["target_brands"] = [brand for brand, _ in names]
    sample["state"].update(source_text=(
        "Maya v1.1.64 is out 💫\n"
        "EXL3 works on AMD APUs paired with NVIDIA GPUs.\n"
        "Also in this release:\n- DeepSeek decoding is back to previous speeds.\n"
        "- Qwen GGUFs now work.\n- Damaged MiniMax files are detected."
    ), tracked_brands=[{"brand_id": brand, "display_name": name, "aliases": [name], "products": [], "accounts": []}
                       for brand, name in names])
    prepared = build_jev(sample, {"entities": []})
    positive = {question for mapping in prepared["metadata"]["question_map"].values()
                for key, question in mapping.items()
                if key in {"relevant", "type:releases_updates", "positive", "identity_namesake_only"}}
    result = finish(sample, prepared, answers(prepared["request"], positive_keys=positive))
    assert result["publication_result"]["valid"]
    for brand, _ in names:
        judgment = result["publication_result"]["by_brand"][brand]
        assert judgment["outcome"] == "classified"
        assert judgment["post_types"] == ["other"]
        assert judgment["sentiment"] == "neutral"


def test_other_product_release_does_not_restore_passing_hardware_release_type():
    from x_monitor.compressed_classifier import build_jev, finish
    sample = case()
    sample["target_brands"] = ["nemo_megatron"]
    sample["state"].update(source_text="Maya is out. It works on AMD APUs paired with NVIDIA GPUs.", tracked_brands=[{
        "brand_id": "nemo_megatron", "display_name": "NVIDIA", "aliases": ["NVIDIA"], "products": [], "accounts": [],
    }])
    document = extraction()
    document["entities"] = []
    finding = document["release_findings"]["findings"][0]
    finding["observed_name"] = "Maya"
    finding["assertions"][0]["assertion_text"] = "Maya is out"
    finding["assertions"][0]["source_excerpt"] = "Maya is out."
    prepared = build_jev(sample, document, release_channels=("api", "weights"))
    response = answers(prepared["request"], positive_keys={"relevant", "positive", "identity_namesake_only", "release:0:concerns:nemo_megatron"})
    result = finish(sample, prepared, response)
    assert result["publication_result"]["valid"], result["contract_errors"]
    assert result["publication_result"]["by_brand"]["nemo_megatron"]["post_types"] == ["other"]
    assert result["publication_result"]["by_brand"]["nemo_megatron"]["sentiment"] == "neutral"


def test_paired_hardware_with_its_own_praise_keeps_supported_sentiment():
    from x_monitor.compressed_classifier import build_jev, finish
    sample = case()
    sample["target_brands"] = ["nemo_megatron"]
    sample["state"].update(source_text="Works with AMD APUs paired with NVIDIA GPUs, which are excellent.", tracked_brands=[{
        "brand_id": "nemo_megatron", "display_name": "NVIDIA", "aliases": ["NVIDIA"], "products": [], "accounts": [],
    }])
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "positive", "identity_namesake_only"})
    result = finish(sample, prepared, response)
    assert result["publication_result"]["by_brand"]["nemo_megatron"]["sentiment"] == "positive"


def test_paired_hardware_without_identity_conflict_keeps_existing_labels():
    from x_monitor.compressed_classifier import build_jev, finish
    sample = case()
    sample["target_brands"] = ["nemo_megatron"]
    sample["state"].update(source_text="Works on AMD APUs paired with NVIDIA GPUs.", tracked_brands=[{
        "brand_id": "nemo_megatron", "display_name": "NVIDIA", "aliases": ["NVIDIA"], "products": [], "accounts": [],
    }])
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "positive", "type:releases_updates"})
    result = finish(sample, prepared, response)
    brand = result["publication_result"]["by_brand"]["nemo_megatron"]
    assert brand["sentiment"] == "positive"
    assert brand["post_types"] == ["releases_updates"]


def test_identity_conflict_does_not_transfer_other_product_launch_or_praise_in_prose():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["state"]["source_text"] = "Maya v1.1.64 is out and excellent. Qwen files now work."
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "identity_namesake_only", "type:releases_updates", "positive"})
    result = finish(sample, prepared, response)
    brand = result["publication_result"]["by_brand"]["qwen"]
    assert brand["outcome"] == "classified"
    assert brand["post_types"] == ["other"]
    assert brand["sentiment"] == "neutral"


def test_identity_conflict_capitalized_description_is_not_a_namesake():
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["state"]["source_text"] = "Qwen Models are excellent."
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={"relevant", "identity_namesake_only", "positive"})
    result = finish(sample, prepared, response)
    brand = result["publication_result"]["by_brand"]["qwen"]
    assert brand["outcome"] == "classified"
    assert brand["sentiment"] == "positive"


@pytest.mark.parametrize("text,types,sentiment", [
    ("Maya is out and excellent with support for Qwen files.", ["other"], "neutral"),
    ("Qwen4 weights are available today.", ["releases_updates"], "positive"),
    ("Maya is out. Qwen files now work and Qwen Models are excellent.", ["other"], "positive"),
])
def test_conflicting_identity_vote_binds_launch_and_praise_to_target(text, types, sentiment):
    from x_monitor.compressed_classifier import build_jev, finish

    sample = case()
    sample["state"]["source_text"] = text
    prepared = build_jev(sample, {"entities": []})
    response = answers(prepared["request"], positive_keys={
        "relevant", "identity_namesake_only", "type:releases_updates", "positive",
    })
    result = finish(sample, prepared, response)
    brand = result["publication_result"]["by_brand"]["qwen"]
    assert brand["outcome"] == "classified"
    assert brand["post_types"] == types
    assert brand["sentiment"] == sentiment

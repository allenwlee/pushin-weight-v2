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
    positives = {identity_question, "relevant", "target_pitch", "positive", "product:testimonial",
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

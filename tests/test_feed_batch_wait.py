from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from core.models import PostEnrichmentState
from monitor.cycle import CycleRunner
from tests.test_post_enrichment_queue import _cfg, _state
from x_monitor import attribution

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _drain(monkeypatch, *, coalesce=True):
    sent = []

    def classify(tweets, *args, **kwargs):
        sent.extend(tweet["tweet_id"] for tweet in tweets)
        return [{"valid": False} for _ in tweets]

    monkeypatch.setattr(attribution, "classify_batch_pragmatics_full", classify)
    runner = CycleRunner(
        cfg=_cfg(), cycle_kind="enrichment",
        _post_fetch_clients={
            "classification": SimpleNamespace(request_profile="deepseek_0731"),
            "translation": None,
        },
    )
    result = runner._process_enrichment_claim_batch(
        [], run_id="remainder-check", fair_queue=True,
        coalesce_feed_batches=coalesce,
    )
    return sent, result


def test_small_batch_waits_and_combines_with_eighteen_new_arrivals(monkeypatch):
    held = {_state("first").pk, _state("second").pk}
    sent, result = _drain(monkeypatch)
    assert sent == []
    assert len(held) == result["n_classification_batch_waiting"] == 2
    assert 0 < result["classification_batch_wait_until"] - timezone.now().timestamp() <= 60
    for state in PostEnrichmentState.objects.filter(pk__in=held):
        assert state.claim_run_id == ""
        assert state.classification_status == "pending"
        assert state.classification_attempts == 0
        assert state.classification_next_attempt_at is None
    sent, result = _drain(monkeypatch)
    assert sent == []
    assert result["n_classification_batch_waiting"] == 2
    for i in range(18):
        _state(f"later-{i}")
    sent, _ = _drain(monkeypatch)
    assert len(sent) == 20 and held.issubset(sent)


def test_expired_oldest_releases_the_whole_tail_even_after_restart(monkeypatch):
    old = _state("old")
    _state("young")
    PostEnrichmentState.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(seconds=61)
    )
    sent, _ = _drain(monkeypatch)
    assert set(sent) == {"old", "young"}


def test_retry_uses_existing_due_time_and_manual_drain_is_immediate(monkeypatch):
    state = _state("retried")
    due = timezone.now() - timedelta(seconds=15)
    PostEnrichmentState.objects.filter(pk=state.pk).update(
        created_at=due - timedelta(days=1),
        classification_next_attempt_at=due,
        classification_attempts=1,
    )
    for _ in range(2):
        sent, result = _drain(monkeypatch)
        assert sent == []
        assert result["classification_batch_wait_until"] == (due + timedelta(seconds=60)).timestamp()
        state.refresh_from_db()
        assert state.classification_next_attempt_at == due
        assert state.classification_attempts == 1
    sent, _ = _drain(monkeypatch, coalesce=False)
    assert sent == ["retried"]


def test_slot_limited_batch_dispatches_without_waiting(monkeypatch):
    from core.models import Brand, PostBrand

    state = _state("many-targets")
    for i in range(98):
        brand = Brand.objects.create(nickname=f"brand-{i}", display_name=f"Brand {i}")
        PostBrand.objects.create(post=state.post, brand=brand)
    sent, _ = _drain(monkeypatch)
    assert sent == ["many-targets"]


@pytest.mark.parametrize("translate", [False, True])
def test_continuous_worker_only_waits_when_it_can_service_the_deadline(monkeypatch, settings, translate):
    import json
    import threading
    from io import StringIO

    from django.core.management import call_command

    from monitor.management.commands import run_enrichment_worker as worker
    from tests.test_literal_translation_plaintext import PlaintextClient, TextResponse
    from tests.test_u18_runtime_0731 import FixedSlotTransport
    from x_monitor import reattribute
    from x_monitor.config import DEEPSEEK_0731_MODEL

    call_command("seed_i18n_labels", verbosity=0)
    state = _state("wait-or-translate", translation_requested=translate)
    state.post.lang = "en"
    state.post.save(update_fields=["lang"])
    if not translate:
        # Queue eligibility checks PostBrand; a saved row can still lack text.
        blank = _state("brand-without-source")
        blank.post.text = ""
        blank.post.save(update_fields=["text"])
    cfg = _cfg()
    cfg.llm.literal_translation_v2_enabled = True
    cfg.llm.classifier_model = DEEPSEEK_0731_MODEL
    cfg.harvest.enrichment.mode = "worker"
    cfg.harvest.enrichment.provider_calls_active = True
    classifier = FixedSlotTransport()
    translator = PlaintextClient([TextResponse("深度求索发布"), TextResponse("DeepSeekのリリース")])
    waits = []

    class StopAfterPoll(threading.Event):
        def wait(self, seconds):
            waits.append(seconds)
            state.refresh_from_db()
            assert not state.claim_run_id
            self.set()
            return True

    monkeypatch.setattr(worker, "threading", SimpleNamespace(
        Event=StopAfterPoll, current_thread=threading.current_thread, main_thread=threading.main_thread,
    ))
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    monkeypatch.setattr(worker, "load_config", lambda path: cfg)
    monkeypatch.setattr(reattribute, "build_classifier_client_from_env", lambda *_: classifier)
    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda *_: translator)
    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    intake = []
    recoveries = []
    monkeypatch.setattr("core.product_release_detection_queue.enqueue_posts", lambda ids: intake.extend(ids))
    monkeypatch.setattr("monitor.pulse_processing.process_saved_findings", lambda: recoveries.append(True))
    monkeypatch.setattr("core.product_release_acquisition.dispatch_due_recovery", lambda: None)
    output = StringIO()
    # A second pass before sleep would otherwise spin for up to 60 real seconds.
    if not translate:
        original = CycleRunner._run_post_fetch
        def only_once(*args, **kwargs):
            assert not recoveries, "wholly deferred pass must yield to the normal poll"
            return original(*args, **kwargs)
        monkeypatch.setattr(CycleRunner, "_run_post_fetch", only_once)
    call_command("run_enrichment_worker", stdout=output)
    assert recoveries
    assert intake == ([state.pk] if translate else [])
    result = json.loads(output.getvalue().splitlines()[1])
    if translate:
        assert "classification_batch_wait_until" not in result
        assert state.translation_status == state.classification_status == "succeeded"
        assert len(translator.calls) == len(classifier.calls) == 2
    else:
        assert result["n_enrichment_claimed"] == 2
        assert result["n_classification_batch_waiting"] == 1
        assert state.classification_status == "pending" and classifier.calls == []
    assert len(waits) == 1 and 0 < waits[0] <= cfg.harvest.enrichment.poll_seconds


@pytest.mark.parametrize("slow_head, targeted", [(False, False), (True, False), (False, True)])
def test_continuous_pass_uses_deadline_for_two_posts_behind_full_batch(monkeypatch, settings, slow_head, targeted):
    import json
    import threading

    from django.core.management import call_command

    from tests.test_u18_runtime_0731 import FixedSlotTransport
    from x_monitor.config import DEEPSEEK_0731_MODEL

    call_command("seed_i18n_labels", verbosity=0)
    ids = {_state(f"original-{i:02}").pk for i in range(22)}
    tail_started = threading.Event()

    class TimedTransport(FixedSlotTransport):
        def messages_create(self, **kwargs):
            size = len(json.loads(kwargs["messages"][0]["content"])["cases"])
            if slow_head and size == 20:
                assert tail_started.wait(8)
            if size == 2:
                tail_started.set()
            reply = super().messages_create(**kwargs)
            if targeted and size == 20 and "CONTENT ROLE:" in kwargs["system"]:
                for choice in reply["decisions"].values():
                    choice["post_types"] = ["events"]
            return reply

    if slow_head:
        # Simulate reaching the timer while head roles are blocked. A separate
        # executor test exercises the actual timer without a full minute's wait.
        def expire(futures, timeout):
            assert 0 < timeout <= 60
            return set(), set(futures)
        monkeypatch.setattr(attribution, "wait", expire)
    settings.X_MONITOR_LLM_PAUSE_SECONDS = 0
    cfg = _cfg()
    cfg.llm.classifier_model = DEEPSEEK_0731_MODEL
    cfg.targeted_extraction.enabled = targeted
    transport = TimedTransport()
    runner = CycleRunner(
        cfg=cfg, cycle_kind="enrichment",
        _post_fetch_clients={"classification": transport, "translation": None},
    )
    if targeted:
        def extract(*_args):
            assert tail_started.is_set()
            return {"records": []}
        runner._targeted_extraction_calls = {"event_extraction": extract, "model_release_extraction": extract}

    def run_worker_pass(run_id):
        return runner._process_enrichment_claim_batch(
            [], run_id=run_id, fair_queue=True, coalesce_feed_batches=True,
        )

    result = run_worker_pass("mixed-pass")
    sizes = sorted(len(call["payload"]["cases"]) for call in transport.calls)
    assert sizes == ([2, 2, 20, 20] if slow_head or targeted else [20, 20])
    if slow_head or targeted:
        assert "classification_batch_wait_until" not in result
        assert result["n_classifications_published"] == len(ids)
        if targeted:
            assert result["n_targeted_extraction_calls"] > 0
            assert not result["targeted_failed_roles"]
    else:
        assert result["n_classification_batch_waiting"] == 2
        held = PostEnrichmentState.objects.filter(pk__in=ids, classification_status="pending")
        assert held.count() == 2
        assert all(s.classification_attempts == 0 and not s.claim_run_id
                   and s.classification_next_attempt_at is None for s in held)
        for i in range(18):
            _state(f"later-{i:02}")
        transport.calls.clear()
        next_result = run_worker_pass("combined")
        assert next_result["n_classifications_published"] == 20
        assert [len(call["payload"]["cases"]) for call in transport.calls] == [20, 20]

from __future__ import annotations

import re
import threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from monitor import post_synthesis
from x_monitor.config import SynthesisConfig, load_config
from x_monitor.provider_telemetry import ProviderTextResponse


def _config(concurrency=2):
    return SynthesisConfig(
        activation_state="owner_override",
        provider_calls_enabled=True,
        control_revision="concurrency-test",
        concurrency=concurrency,
    )


def test_checked_in_synthesis_uses_two_configurable_slots():
    assert load_config(Path("config.yaml")).synthesis.concurrency == 2
    for slots in (1, 2, 5, 20):
        assert SynthesisConfig(concurrency=slots, batch_size=20).concurrency == slots
    for slots in (0, 21):
        with pytest.raises(ValueError):
            SynthesisConfig(concurrency=slots, batch_size=20)
    with pytest.raises(ValueError, match="batch_size must be at least concurrency"):
        SynthesisConfig(concurrency=6, batch_size=5)


@pytest.mark.parametrize("slots,fail_one", [(1, False), (2, False), (2, True)])
def test_real_synthesis_calls_overlap_with_database_work_on_owner_thread(
    monkeypatch, slots, fail_one
):
    owner_thread = threading.get_ident()
    demands = [
        SimpleNamespace(
            pk=i,
            post_id=f"parallel-{i}",
            post=f"parallel-{i}",
            input_context_fingerprint="source",
            lease_owner="worker",
            lease_fence=1,
        )
        for i in range(slots)
    ]
    published = []
    failures = []
    limits = []

    def claim(**kwargs):
        assert threading.get_ident() == owner_thread
        limits.append(kwargs.get("limit"))
        return demands

    def context(post):
        assert threading.get_ident() == owner_thread
        return {"source": post, "stored_quote": "", "local_parent": ""}, "source", []

    def publish(**kwargs):
        assert threading.get_ident() == owner_thread
        assert set(kwargs["response"].texts) == {"en", "zh-cn", "ja"}
        published.append(kwargs["demand_id"])
        return object()

    def fail(**kwargs):
        assert threading.get_ident() == owner_thread
        failures.append(kwargs)
        return True

    monkeypatch.setattr(post_synthesis, "claim_synthesis_demands", claim)
    monkeypatch.setattr(post_synthesis, "post_context", context)
    monkeypatch.setattr(post_synthesis, "publish_claimed_synthesis", publish)
    monkeypatch.setattr(post_synthesis, "fail_synthesis_claim", fail)
    barrier = threading.Barrier(slots)
    lock = threading.Lock()

    class Client:
        active = 0
        peak = 0
        calls = 0

        def messages_create_text(self, **kwargs):
            assert threading.get_ident() != owner_thread
            with lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
                self.calls += 1
            try:
                barrier.wait(timeout=2)
                post_id = re.search(r"parallel-\d+", kwargs["messages"][0]["content"])[
                    0
                ]
                if fail_one and post_id == "parallel-0":
                    raise TimeoutError("fake provider timeout")
                return ProviderTextResponse(
                    text=(
                        f"[[POST_ID]]{post_id}[[/POST_ID]]\n"
                        "[[EN]]The author announces a new release.[[/EN]]\n"
                        "[[ZH_CN]]作者宣布了一项新发布。[[/ZH_CN]]\n"
                        "[[JA]]著者は新しいリリースを発表しています。[[/JA]]"
                    ),
                    provider_usage={"input_tokens": 42, "output_tokens": 24},
                )
            finally:
                with lock:
                    self.active -= 1

    client = Client()
    result = post_synthesis.process_synthesis_batch(
        config=_config(slots), client=client
    )

    assert result == {
        "status": "processed",
        "claimed": slots,
        "succeeded": slots - int(fail_one),
        "failed": int(fail_one),
        "cancelled": 0,
    }
    assert client.peak == slots
    assert client.calls == slots
    assert limits == [slots]
    assert len(published) == slots - int(fail_one)
    if fail_one:
        assert failures[0]["error_code"] == "transport_timeout"


def test_disabled_synthesis_never_claims_or_dispatches(monkeypatch):
    def forbidden(**kwargs):
        pytest.fail("disabled synthesis claimed work")

    monkeypatch.setattr(post_synthesis, "claim_synthesis_demands", forbidden)
    result = post_synthesis.process_synthesis_batch(
        config=SynthesisConfig(), client=object()
    )
    assert result["status"] == "provider_disabled"
    assert result["claimed"] == 0


def test_worker_only_waits_when_no_work_was_claimed(monkeypatch):
    from monitor.management.commands import run_synthesis_worker as worker

    monkeypatch.setenv("DATABASE_URL", "postgresql://test.invalid/unused")
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "staging")
    monkeypatch.setattr(
        worker, "load_config", lambda path: SimpleNamespace(synthesis=_config())
    )
    monkeypatch.setattr(worker, "build_synthesis_client", lambda config: object())
    monkeypatch.setattr(
        worker, "acquire_synthesis_coordination_lock", lambda *a, **k: nullcontext()
    )
    results = iter(
        [
            {"claimed": 2, "succeeded": 2, "failed": 0},
            {"claimed": 0, "succeeded": 0, "failed": 0},
        ]
    )
    monkeypatch.setattr(worker, "process_synthesis_batch", lambda **kw: next(results))
    sleeps = []
    monkeypatch.setattr(worker.time, "sleep", sleeps.append)

    with pytest.raises(StopIteration):
        worker.Command().handle(once=False, as_json=True)

    assert sleeps == [_config().poll_seconds]

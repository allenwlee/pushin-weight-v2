"""A small remainder may use an existing scheduled executor at its readiness deadline."""

import json
import threading
import time
from collections import Counter

from monitor.cycle import _BoundedClassifierClient
from tests.test_u18a_classifier_contract_v4 import _SelectedTransport
from x_monitor.attribution import classify_batch_pragmatics_full


def _posts():
    return [
        {"tweet_id": str(n), "text": "Testing DeepSeek", "brand_ids": ["deepseek"]}
        for n in range(22)
    ]


def _guard(transport):
    reservations = []
    returned_attempts = []
    client = _BoundedClassifierClient(
        transport,
        maximum_calls=24,
        pause_seconds=0,
        reserve_pair_budget=lambda bounds, attempts: reservations.append((len(bounds), attempts)),
        release_pair_budget=returned_attempts.append,
    )
    return client, reservations, returned_attempts


def test_fast_full_batch_returns_markers_for_the_tail_without_spending_its_budget():
    transport = _SelectedTransport()
    client, reservations, returned = _guard(transport)
    due = time.time() + 5
    tails = []

    def deadline(batch):
        tails.append([post["tweet_id"] for post in batch])
        return due

    results = classify_batch_pragmatics_full(_posts(), [], client, tail_wait_deadline=deadline)

    assert tails == [["20", "21"]]
    assert results[-2:] == [{"batch_wait_until": due}] * 2
    assert all(r["valid"] and set(r["by_brand"]) == {"deepseek"} for r in results[:-2])
    assert Counter((len(c["payload"]["cases"]), c["content"]) for c in transport.calls) == {
        (20, True): 1, (20, False): 1,
    }
    assert len(reservations) == 1 and reservations[0][0] == 2
    assert sum(returned) == reservations[0][1] * 2 - 2
    assert client.remaining_calls == 22


def test_tail_runs_at_expiry_while_full_batch_roles_are_still_in_flight():
    tail_started = threading.Event()
    full_roles_saw_tail = []
    times = []
    deadlines = []

    class Transport(_SelectedTransport):
        def messages_create(self, **kwargs):
            cases = json.loads(kwargs["messages"][0]["content"])["cases"]
            if len(cases) == 20:
                full_roles_saw_tail.append(tail_started.wait(timeout=3))
            else:
                times.append(time.time())
                tail_started.set()
            return super().messages_create(**kwargs)

    transport = Transport()
    client, reservations, returned = _guard(transport)

    def deadline(batch):
        assert [p["tweet_id"] for p in batch] == ["20", "21"]
        deadlines.append(time.time() + 0.15)
        return deadlines[-1]

    results = classify_batch_pragmatics_full(
        _posts(), [], client, max_workers=3, tail_wait_deadline=deadline,
    )

    assert full_roles_saw_tail == [True, True]
    assert len(deadlines) == 1 and len(times) == 2 and min(times) >= deadlines[0]
    assert all(r["valid"] and set(r["by_brand"]) == {"deepseek"} for r in results)
    assert Counter((len(c["payload"]["cases"]), c["content"]) for c in transport.calls) == {
        (20, True): 1, (20, False): 1, (2, True): 1, (2, False): 1,
    }
    assert [role_count for role_count, _ in reservations] == [2, 2]
    assert sum(returned) == sum(2 * attempts for _, attempts in reservations) - 4
    assert client.remaining_calls == 20


def test_expired_tail_queues_behind_two_occupied_executor_slots():
    tail_admitted = threading.Event()
    full_completed = threading.Event()
    head_saw_admission = []
    tail_saw_completion = []

    def reserve(bounds, attempts):
        first_role_packet = json.loads(bounds[0]["messages"][0]["content"])
        if len(first_role_packet["cases"]) == 2:
            tail_admitted.set()

    class Transport(_SelectedTransport):
        def messages_create(self, **kwargs):
            cases = json.loads(kwargs["messages"][0]["content"])["cases"]
            if len(cases) == 20:
                head_saw_admission.append(tail_admitted.wait(timeout=3))
                full_completed.set()
            else:
                tail_saw_completion.append(full_completed.is_set())
            return super().messages_create(**kwargs)

    transport = Transport()
    client = _BoundedClassifierClient(
        transport, maximum_calls=24, pause_seconds=0, reserve_pair_budget=reserve,
    )
    results = classify_batch_pragmatics_full(
        _posts(), [], client, max_workers=2, tail_wait_deadline=lambda _: time.time() + 0.15,
    )

    assert head_saw_admission == [True, True]
    assert tail_saw_completion == [True, True]
    assert sum(r["valid"] for r in results) == 22
    assert client.calls == 4
    assert client.remaining_calls == 20

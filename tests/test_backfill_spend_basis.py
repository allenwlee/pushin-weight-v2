"""Classification spend admission on the reservation and settled bases.

A backfill enrichment policy's ``max_usd`` limit is checked when each model
request is admitted. Policies without ``spend_basis`` (every policy frozen
before this option existed, including July's) count conservative reservations
only. ``spend_basis: "settled"`` counts provider-reported cost for finished
requests and the reservation for everything else.

These tests need no database. The real admission path is pinned by the
PostgreSQL tests in ``tests/test_backfill_direct_enrichment.py`` and
``tests/test_backfill_native_enrichment.py``.
"""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.provider_batches import (
    BatchAdmissionError,
    admit_model_request,
    counted_model_spend,
    enrichment_policy_definition,
)
from monitor.backfill_enrichment import policy_snapshot
from x_monitor.deepinfra import DEEPSEEK_0731_MODEL, GEMMA_4_31B_MODEL


def call(state, reserved, actual=None):
    """One OriginalContentCall as admission reads it."""
    return {
        "state": state,
        "reserved": Decimal(reserved),
        "actual": None if actual is None else Decimal(actual),
    }


# Two finished requests reserved $6 in total and cost $1; one is still in flight.
FINISHED_AND_IN_FLIGHT = [
    call("completed", "4.00", "0.75"),
    call("completed", "2.00", "0.25"),
    call("sent", "0.50"),
]


def today_snapshot(deadline, *, max_usd, max_model_requests, max_control_requests):
    """policy_snapshot's output before spend_basis existed, in its key order."""
    return {
        "version": 1,
        "max_usd": max_usd,
        "deadline": deadline.isoformat(),
        "max_model_requests": max_model_requests,
        "max_control_requests": max_control_requests,
        "max_attempts": 3,
        "prices": {
            GEMMA_4_31B_MODEL: ["0.09", "0.34"],
            DEEPSEEK_0731_MODEL: ["0.06", "0.18"],
        },
        "selection": [],
        "max_file_requests": 2000,
        "max_file_bytes": 16 * 1024 * 1024,
    }


# --- policy_snapshot -------------------------------------------------------


def test_snapshot_without_spend_basis_is_byte_identical_to_today():
    # Frozen policies are compared as dicts later; adding even a default key
    # would make July's saved policy look changed.
    deadline = timezone.now() + timedelta(hours=72)
    snapshot = policy_snapshot(max_usd="5", deadline=deadline)
    expected = today_snapshot(
        deadline, max_usd="5", max_model_requests=20000, max_control_requests=5000
    )
    assert json.dumps(snapshot) == json.dumps(expected)
    assert "spend_basis" not in snapshot


def test_campaign_style_snapshot_without_spend_basis_is_byte_identical_to_today():
    # The keyword form scripts/backfill_campaign.py used before this change.
    deadline = timezone.now() + timedelta(days=30)
    snapshot = policy_snapshot(
        max_usd="30",
        deadline=deadline,
        max_model_requests=1000000,
        max_control_requests=5000,
    )
    expected = today_snapshot(
        deadline, max_usd="30", max_model_requests=1000000, max_control_requests=5000
    )
    assert json.dumps(snapshot) == json.dumps(expected)


@pytest.mark.parametrize("basis", ["reservation", "settled"])
def test_snapshot_carries_an_explicit_spend_basis(basis):
    deadline = timezone.now() + timedelta(hours=6)
    snapshot = policy_snapshot(max_usd="30", deadline=deadline, spend_basis=basis)
    expected = today_snapshot(
        deadline, max_usd="30", max_model_requests=20000, max_control_requests=5000
    )
    assert snapshot == expected | {"spend_basis": basis}


@pytest.mark.parametrize("basis", ["actual", "", "Settled", "settled ", 1, ["settled"]])
def test_unknown_spend_basis_is_rejected_when_the_policy_is_created(basis):
    with pytest.raises(BatchAdmissionError, match="^enrichment_spend_basis_invalid$"):
        policy_snapshot(
            max_usd="30",
            deadline=timezone.now() + timedelta(hours=6),
            spend_basis=basis,
        )


def test_spend_basis_is_part_of_the_frozen_policy_definition():
    # A job frozen without the key cannot later resume on the settled basis:
    # execute_enrichment compares these definitions and refuses a change.
    deadline = timezone.now() + timedelta(hours=6)
    frozen = policy_snapshot(max_usd="30", deadline=deadline)
    settled = policy_snapshot(max_usd="30", deadline=deadline, spend_basis="settled")
    assert enrichment_policy_definition(frozen) != enrichment_policy_definition(settled)


# --- counted spend ---------------------------------------------------------


def test_settled_basis_counts_provider_cost_for_finished_requests():
    assert counted_model_spend(FINISHED_AND_IN_FLIGHT, "settled") == Decimal("1.50")


@pytest.mark.parametrize("basis", [None, "reservation"])
def test_reservation_basis_counts_every_reservation(basis):
    assert counted_model_spend(FINISHED_AND_IN_FLIGHT, basis) == Decimal("6.50")


def test_completed_request_without_provider_cost_counts_its_reservation():
    rows = [call("completed", "6.00", "1.00"), call("completed", "2.00")]
    assert counted_model_spend(rows, "settled") == Decimal("3.00")


@pytest.mark.parametrize("state", ["reserved", "sent", "ambiguous", "failed"])
def test_unfinished_failed_and_ambiguous_requests_count_their_reservation(state):
    # Even a recorded cost does not replace the reservation outside "completed".
    rows = [call(state, "0.40", "0.01"), call(state, "0.10")]
    assert counted_model_spend(rows, "settled") == Decimal("0.50")


def test_no_requests_count_zero():
    assert counted_model_spend([], "settled") == Decimal(0)
    assert counted_model_spend([], None) == Decimal(0)


@pytest.mark.parametrize("basis", ["actual", "", 1])
def test_unknown_spend_basis_in_a_saved_policy_stops_admission(basis):
    with pytest.raises(BatchAdmissionError, match="^enrichment_spend_basis_invalid$"):
        counted_model_spend(FINISHED_AND_IN_FLIGHT, basis)


# --- admission -------------------------------------------------------------

POLICY = {"max_usd": "30", "max_model_requests": 20000}


def test_settled_spend_near_the_limit_refuses_the_next_reservation():
    rows = [call("completed", "150.00", "29.70"), call("sent", "0.20")]
    counted = counted_model_spend(rows, "settled")
    assert counted == Decimal("29.90")
    with pytest.raises(
        BatchAdmissionError, match="^model_campaign_allowance_exhausted$"
    ):
        admit_model_request(
            POLICY, count=2, counted_usd=counted, reservation_usd=Decimal("0.20")
        )


def test_reservation_reaching_the_limit_exactly_is_admitted():
    assert admit_model_request(
        POLICY,
        count=2,
        counted_usd=Decimal("29.80"),
        reservation_usd=Decimal("0.20"),
    ) == (3, Decimal("30.00"))


def test_request_count_limit_still_applies():
    with pytest.raises(
        BatchAdmissionError, match="^model_campaign_allowance_exhausted$"
    ):
        admit_model_request(
            {"max_usd": "30", "max_model_requests": 2},
            count=2,
            counted_usd=Decimal(0),
            reservation_usd=Decimal("0.01"),
        )


def test_same_requests_settled_basis_admits_where_reservation_basis_refuses():
    # October reservations ran 6-7x provider cost; this is the gap KTD6 closes.
    rows = [call("completed", "29.00", "4.50"), call("ambiguous", "0.30")]
    policy = {"max_usd": "10", "max_model_requests": 20000}
    admitted = admit_model_request(
        policy,
        count=2,
        counted_usd=counted_model_spend(rows, "settled"),
        reservation_usd=Decimal("0.20"),
    )
    assert admitted == (3, Decimal("5.00"))
    with pytest.raises(
        BatchAdmissionError, match="^model_campaign_allowance_exhausted$"
    ):
        admit_model_request(
            policy,
            count=2,
            counted_usd=counted_model_spend(rows, None),
            reservation_usd=Decimal("0.20"),
        )

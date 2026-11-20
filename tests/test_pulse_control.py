"""Local control-file behavior; no claim of production shared storage."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest


def store(tmp_path):
    from monitor.pulse_control import initialize

    initialize(directory=tmp_path, state="running", actor="operator", reason="local test")
    return tmp_path


def test_unconfigured_or_missing_store_never_reports_running(settings, tmp_path):
    from monitor.pulse_control import read_status

    settings.PULSE_CONTROL_DIRECTORY = ""
    assert read_status()["status"] == "unavailable"
    assert read_status()["acknowledged_revision"] is None
    assert read_status(directory=tmp_path)["status"] == "unavailable"
    assert list(tmp_path.iterdir()) == []


def test_request_and_acknowledgement_are_distinct_and_replay_safe(tmp_path):
    from monitor.pulse_control import acknowledge, read_status, request_state

    directory = store(tmp_path)
    assert read_status(directory=directory)["status"] == "resume_requested"
    running = acknowledge(1, boundary="before_identity", directory=directory)
    assert running["status"] == "running"
    stopped = request_state("stopped", expected_revision=1, actor="operator", reason="wrong match", directory=directory)
    assert stopped["status"] == "stop_requested"
    assert stopped["acknowledged_state"] == "running"
    assert stopped["acknowledged_revision"] == 1
    acknowledged = acknowledge(2, boundary="before_identity", directory=directory)
    assert acknowledged["status"] == "stopped"
    replayed = acknowledge(2, boundary="before_identity", directory=directory)
    assert replayed["acknowledged_at"] == acknowledged["acknowledged_at"]
    assert replayed["desired_revision"] == 2
    assert acknowledged["requested_at"].endswith("+09:00")


def test_concurrent_requests_accept_one_revision_and_reject_stale_ack(tmp_path):
    from monitor.pulse_control import PulseControlConflict, acknowledge, request_state

    directory = store(tmp_path)

    def request():
        try:
            return request_state("stopped", expected_revision=1, actor="operator", reason="stop", directory=directory)["desired_revision"]
        except PulseControlConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(lambda _: request(), range(2)), key=str) == [2, "conflict"]
    with pytest.raises(PulseControlConflict):
        acknowledge(1, boundary="before_identity", directory=directory)


@pytest.mark.parametrize("value", [True, 0, -1, "1"])
def test_request_rejects_invalid_revision_without_mutation(tmp_path, value):
    from monitor.pulse_control import request_state

    directory = store(tmp_path)
    before = (directory / "pulse-control.json").read_bytes()
    with pytest.raises(ValueError):
        request_state("stopped", expected_revision=value, actor="operator", reason="stop", directory=directory)
    assert (directory / "pulse-control.json").read_bytes() == before


def test_corrupt_unknown_or_oversized_state_is_visible_and_not_replaced(tmp_path):
    from monitor.pulse_control import (
        MAX_FILE_BYTES,
        PulseControlUnavailable,
        read_status,
        request_state,
    )

    directory = store(tmp_path)
    path = directory / "pulse-control.json"
    valid = json.loads(path.read_text())
    for content in ("{broken", json.dumps({**valid, "unknown": True}), "x" * (MAX_FILE_BYTES + 1)):
        path.write_text(content)
        assert read_status(directory=directory)["status"] == "unavailable"
        with pytest.raises(PulseControlUnavailable):
            request_state("stopped", expected_revision=1, actor="operator", reason="stop", directory=directory)
        assert path.read_text() == content


def test_failed_atomic_replace_preserves_last_control_state(tmp_path, monkeypatch):
    from monitor import pulse_control

    directory = store(tmp_path)
    before = (directory / "pulse-control.json").read_bytes()

    def fail(*args):
        raise OSError("local storage error")

    monkeypatch.setattr(pulse_control.os, "replace", fail)
    with pytest.raises(pulse_control.PulseControlUnavailable):
        pulse_control.request_state("stopped", expected_revision=1, actor="operator", reason="stop", directory=directory)
    assert (directory / "pulse-control.json").read_bytes() == before
    assert not list(directory.glob(".pulse-write-*"))


def test_deeply_nested_corrupt_control_is_unavailable_and_preserved(tmp_path):
    from monitor.pulse_control import (
        PulseControlUnavailable,
        read_status,
        request_state,
    )

    path = tmp_path / "pulse-control.json"
    content = "[" * 10000 + "]" * 10000
    path.write_text(content)
    assert read_status(directory=tmp_path)["status"] == "unavailable"
    with pytest.raises(PulseControlUnavailable):
        request_state("stopped", expected_revision=1, actor="fixture", reason="stop", directory=tmp_path)
    assert path.read_text() == content


def test_diagnostics_are_bounded_and_do_not_request_a_stop(tmp_path):
    from monitor.pulse_control import (
        MAX_DIAGNOSTICS,
        acknowledge,
        read_status,
        record_diagnostic,
    )

    directory = store(tmp_path)
    acknowledge(1, boundary="before_identity", directory=directory)
    for i in range(MAX_DIAGNOSTICS + 2):
        record_diagnostic(stage="identity", code="unexpected_product_count", message="Observed count exceeds fixture expectation", references={"post_id": str(i)}, observed=3, expected=1, directory=directory)
    snapshot = read_status(directory=directory)
    assert snapshot["status"] == "running"
    assert snapshot["desired_revision"] == 1
    assert len(snapshot["diagnostics"]) == MAX_DIAGNOSTICS
    assert snapshot["discarded_diagnostics"] == 2
    assert snapshot["diagnostics"][0]["references"]["post_id"] == "2"


def test_initialization_never_overwrites_existing_control(tmp_path):
    from monitor.pulse_control import PulseControlConflict, initialize

    directory = store(tmp_path)
    before = (directory / "pulse-control.json").read_bytes()
    with pytest.raises(PulseControlConflict):
        initialize(directory=directory, state="stopped", actor="operator", reason="initialize again")
    assert (directory / "pulse-control.json").read_bytes() == before


def test_non_ascii_diagnostics_also_respect_byte_retention_limit(tmp_path):
    from monitor.pulse_control import MAX_FILE_BYTES, record_diagnostic

    directory = store(tmp_path)
    for _ in range(100):
        snapshot = record_diagnostic(
            stage="identity", code="unexpected_result", message="異" * 512,
            observed="異" * 256, expected="異" * 256,
            references={key: "異" * 128 for key in ("event_id", "product_key", "post_id", "run_id", "claim_id")},
            directory=directory,
        )
    assert (directory / "pulse-control.json").stat().st_size <= MAX_FILE_BYTES
    assert snapshot["discarded_diagnostics"] > 0
    assert len(snapshot["diagnostics"]) + snapshot["discarded_diagnostics"] == 100

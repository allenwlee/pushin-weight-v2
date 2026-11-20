"""Explicitly configured, local file control for Pulse processing.

This store does not connect separate services. A deployment must supply and
verify that transport before presenting this as control of a remote processor.
Errors record diagnostics; only an operator request changes the desired state.
"""

from __future__ import annotations

import fcntl
import json
import math
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MAX_FILE_BYTES = 262_144
MAX_DIAGNOSTICS = 100
_STATES = {"running", "stopped"}
_FIELDS = {
    "schema_version", "desired_state", "desired_revision", "acknowledged_state",
    "acknowledged_revision", "requested_at", "requested_by", "reason",
    "acknowledged_at", "boundary", "diagnostics", "discarded_diagnostics",
}
_DIAGNOSTIC_FIELDS = {
    "id", "reported_at", "stage", "code", "message", "references", "observed", "expected",
}
_REFERENCE_FIELDS = {"event_id", "product_key", "post_id", "run_id", "claim_id"}


class PulseControlUnavailable(RuntimeError):
    """The configured store cannot safely provide or accept control state."""


class PulseControlConflict(RuntimeError):
    """The caller acted on a control revision which is no longer current."""


def _now():
    return datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="microseconds")


def _text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("invalid_control_text")
    return value


def _revision(value):
    if type(value) is not int or value < 1:
        raise ValueError("invalid_control_revision")
    return value


def _timestamp(value):
    if not isinstance(value, str) or datetime.fromisoformat(value).utcoffset() is None:
        raise ValueError("invalid_control_timestamp")


def _measurement(value):
    if value is None:
        return
    if type(value) in (int, float) and math.isfinite(value):
        return
    _text(value, 256)


def _validate_diagnostic(row):
    if not isinstance(row, dict) or set(row) != _DIAGNOSTIC_FIELDS:
        raise ValueError("invalid_diagnostic_shape")
    uuid.UUID(_text(row["id"], 36))
    _timestamp(row["reported_at"])
    for field in ("stage", "code"):
        _text(row[field], 64)
    _text(row["message"], 512)
    refs = row["references"]
    if not isinstance(refs, dict) or not set(refs) <= _REFERENCE_FIELDS:
        raise ValueError("invalid_diagnostic_references")
    for value in refs.values():
        _text(value, 128)
    _measurement(row["observed"])
    _measurement(row["expected"])


def _validate(row):
    if not isinstance(row, dict) or set(row) != _FIELDS:
        raise ValueError("invalid_control_shape")
    if type(row["schema_version"]) is not int or row["schema_version"] != 1:
        raise ValueError("unknown_control_schema")
    if row["desired_state"] not in _STATES:
        raise ValueError("invalid_control_state")
    _revision(row["desired_revision"])
    _timestamp(row["requested_at"])
    _text(row["requested_by"], 128)
    _text(row["reason"], 1000)
    acknowledged = row["acknowledged_revision"]
    if acknowledged is None:
        if any(row[key] is not None for key in ("acknowledged_state", "acknowledged_at", "boundary")):
            raise ValueError("invalid_control_acknowledgement")
    else:
        _revision(acknowledged)
        if acknowledged > row["desired_revision"] or row["acknowledged_state"] not in _STATES:
            raise ValueError("invalid_control_acknowledgement")
        if acknowledged == row["desired_revision"] and row["acknowledged_state"] != row["desired_state"]:
            raise ValueError("conflicting_control_acknowledgement")
        _timestamp(row["acknowledged_at"])
        _text(row["boundary"], 128)
    if not isinstance(row["diagnostics"], list) or len(row["diagnostics"]) > MAX_DIAGNOSTICS:
        raise ValueError("invalid_control_diagnostics")
    for diagnostic in row["diagnostics"]:
        _validate_diagnostic(diagnostic)
    if type(row["discarded_diagnostics"]) is not int or row["discarded_diagnostics"] < 0:
        raise ValueError("invalid_control_retention")
    return row


def _directory(directory):
    if directory is None:
        from django.conf import settings

        directory = getattr(settings, "PULSE_CONTROL_DIRECTORY", "")
    if not directory:
        raise PulseControlUnavailable("control_unconfigured")
    path = Path(directory)
    if not path.is_absolute():
        raise PulseControlUnavailable("control_directory_not_absolute")
    return path


def _read(directory):
    try:
        with (directory / "pulse-control.json").open("rb") as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("oversized_control_file")
        return _validate(json.loads(data))
    except FileNotFoundError as exc:
        raise PulseControlUnavailable("control_missing") from exc
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise PulseControlUnavailable("control_unreadable_or_invalid") from exc


@contextmanager
def _locked(directory):
    stream = None
    try:
        stream = (directory / ".pulse-control.lock").open("a+b")
        os.fchmod(stream.fileno(), 0o600)
        deadline = time.monotonic() + 0.5
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise PulseControlUnavailable("control_busy")
                time.sleep(0.01)
        yield
    except OSError as exc:
        raise PulseControlUnavailable("control_storage_error") from exc
    finally:
        if stream is not None:
            stream.close()


def _write(directory, row):
    _validate(row)
    data = json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    while len(data) > MAX_FILE_BYTES and row["diagnostics"]:
        row["diagnostics"].pop(0)
        row["discarded_diagnostics"] += 1
        data = json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    if len(data) > MAX_FILE_BYTES:
        raise PulseControlUnavailable("control_file_limit")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".pulse-write-", dir=directory, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, directory / "pulse-control.json")
        with _directory_handle(directory) as descriptor:
            os.fsync(descriptor)
    except OSError as exc:
        raise PulseControlUnavailable("control_write_failed") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def _directory_handle(directory):
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def _snapshot(row):
    acknowledged = row["acknowledged_revision"] == row["desired_revision"]
    status = row["desired_state"] if acknowledged else (
        "stop_requested" if row["desired_state"] == "stopped" else "resume_requested"
    )
    return {**row, "status": status, "observed_at": _now(), "error": None}


def read_status(*, directory=None):
    """Read without creating a directory, lock, or default running state."""
    try:
        return _snapshot(_read(_directory(directory)))
    except PulseControlUnavailable as exc:
        empty = dict.fromkeys(_FIELDS)
        empty.update(schema_version=1, diagnostics=[], discarded_diagnostics=0)
        return {**empty, "status": "unavailable", "observed_at": _now(), "error": str(exc)}


def initialize(*, directory, state, actor, reason):
    """Explicit operator/test setup; never called by readers or request handlers."""
    root = _directory(directory)
    row = dict.fromkeys(_FIELDS)
    row.update(schema_version=1, desired_state=state, desired_revision=1,
               requested_at=_now(), requested_by=actor, reason=reason,
               diagnostics=[], discarded_diagnostics=0)
    _validate(row)
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise PulseControlUnavailable("control_directory_unavailable") from exc
    with _locked(root):
        if (root / "pulse-control.json").exists():
            raise PulseControlConflict("control_already_initialized")
        _write(root, row)
    return _snapshot(row)


def request_state(state, *, expected_revision, actor, reason, directory=None):
    """Record an explicit user request without claiming processor acknowledgement."""
    _revision(expected_revision)
    if state not in _STATES:
        raise ValueError("invalid_control_state")
    _text(actor, 128)
    _text(reason, 1000)
    root = _directory(directory)
    with _locked(root):
        row = _read(root)
        if row["desired_revision"] != expected_revision:
            raise PulseControlConflict("control_revision_changed")
        row.update(desired_state=state, desired_revision=expected_revision + 1,
                   requested_at=_now(), requested_by=actor, reason=reason)
        _write(root, row)
    return _snapshot(row)


def acknowledge(revision, *, boundary, directory=None):
    """Processor-only acknowledgement after observing this revision at a safe boundary."""
    _revision(revision)
    _text(boundary, 128)
    root = _directory(directory)
    with _locked(root):
        row = _read(root)
        if row["desired_revision"] != revision:
            raise PulseControlConflict("control_revision_changed")
        if row["acknowledged_revision"] != revision:
            row.update(acknowledged_state=row["desired_state"], acknowledged_revision=revision,
                       acknowledged_at=_now(), boundary=boundary)
            _write(root, row)
    return _snapshot(row)


def record_diagnostic(*, stage, code, message, references=None, observed=None, expected=None, directory=None):
    """Keep bounded operational summaries, never full prompts or source payloads."""
    diagnostic = {
        "id": str(uuid.uuid4()), "reported_at": _now(), "stage": stage, "code": code,
        "message": message, "references": {} if references is None else references,
        "observed": observed, "expected": expected,
    }
    _validate_diagnostic(diagnostic)
    root = _directory(directory)
    with _locked(root):
        row = _read(root)
        row["diagnostics"].append(diagnostic)
        removed = max(0, len(row["diagnostics"]) - MAX_DIAGNOSTICS)
        row["diagnostics"] = row["diagnostics"][-MAX_DIAGNOSTICS:]
        row["discarded_diagnostics"] += removed
        _write(root, row)
    return _snapshot(row)

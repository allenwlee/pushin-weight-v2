"""Shared control document semantics without external storage calls."""
import hashlib
import io
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from botocore.exceptions import ClientError


class FakeR2:
    def __init__(self):
        self.body = None
        self.lock = threading.Lock()
        self.writes = 0

    def _etag(self):
        return '"' + hashlib.sha256(self.body).hexdigest() + '"'

    def get_object(self, *, Bucket, Key):
        with self.lock:
            if self.body is None:
                raise ClientError({'Error': {'Code': 'NoSuchKey'}, 'ResponseMetadata': {'HTTPStatusCode': 404}}, 'GetObject')
            return {'Body': io.BytesIO(self.body), 'ETag': self._etag()}

    def put_object(self, *, Bucket, Key, Body, **kwargs):
        with self.lock:
            if (kwargs.get('IfNoneMatch') == '*' and self.body is not None) or (
                'IfMatch' in kwargs and (self.body is None or kwargs['IfMatch'] != self._etag())
            ):
                raise ClientError({'Error': {'Code': 'PreconditionFailed'}, 'ResponseMetadata': {'HTTPStatusCode': 412}}, 'PutObject')
            self.body = Body
            self.writes += 1


@pytest.fixture
def shared_store(settings, monkeypatch):
    from monitor import pulse_control_r2

    settings.PULSE_CONTROL_R2_BUCKET = 'pushinweight-media-staging'
    settings.PULSE_CONTROL_R2_KEY = 'pulse/control-v1.json'
    settings.R2_ACCOUNT_ID = 'a' * 32
    settings.R2_ACCESS_KEY_ID = 'test-access'
    settings.R2_SECRET_ACCESS_KEY = 'test-secret'
    client = FakeR2()
    monkeypatch.setattr(pulse_control_r2, '_client', lambda *_: client)
    return client


def test_shared_control_is_explicit_and_acknowledges_safe_boundaries(shared_store):
    from monitor.pulse_control import (
        acknowledge,
        initialize,
        read_status,
        request_state,
    )

    assert read_status()['status'] == 'unavailable'
    assert shared_store.writes == 0
    assert initialize(state='running', actor='operator', reason='staging test')['status'] == 'resume_requested'
    assert acknowledge(1, boundary='between_identity_posts')['status'] == 'running'
    assert request_state('stopped', expected_revision=1, actor='operator', reason='test')['status'] == 'stop_requested'
    assert acknowledge(2, boundary='between_identity_posts')['status'] == 'stopped'
    assert read_status()['status'] == 'stopped'


def test_concurrent_stop_requests_cannot_overwrite_each_other(shared_store):
    from monitor.pulse_control import (
        PulseControlConflict,
        initialize,
        read_status,
        request_state,
    )

    initialize(state='running', actor='operator', reason='test')

    def stop(_):
        try:
            return request_state('stopped', expected_revision=1, actor='operator', reason='test')['desired_revision']
        except PulseControlConflict:
            return 'conflict'

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(stop, range(2)))
    assert results.count(2) == 1 and results.count('conflict') == 1
    assert read_status()['desired_revision'] == 2


def test_bad_shared_document_is_not_replaced(shared_store):
    from monitor.pulse_control import (
        PulseControlUnavailable,
        read_status,
        request_state,
    )

    shared_store.body = b'{bad json'
    assert read_status()['status'] == 'unavailable'
    with pytest.raises(PulseControlUnavailable):
        request_state('running', expected_revision=1, actor='operator', reason='test')
    assert shared_store.body == b'{bad json' and shared_store.writes == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_shared_stop_is_acknowledged_between_identity_units(shared_store):
    from monitor.pulse_control import initialize, read_status, request_state
    from monitor.pulse_processing import identity_application

    initialize(state='running', actor='operator', reason='test')
    with identity_application() as boundary:
        assert boundary.status == 'running'
        request_state('stopped', expected_revision=1, actor='operator', reason='stop')
        assert read_status()['status'] == 'stop_requested'
        assert not boundary.allowed()
        assert read_status()['status'] == 'stopped'

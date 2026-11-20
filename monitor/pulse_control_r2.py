"""Shared, conditional object-file storage for Pulse operational control."""
from __future__ import annotations

import json
import re
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings


def configured(directory):
    return directory is None and bool(getattr(settings, 'PULSE_CONTROL_R2_BUCKET', ''))


@lru_cache(maxsize=4)
def _client(account, access, secret):
    return boto3.client('s3', endpoint_url=f'https://{account}.r2.cloudflarestorage.com',
                        aws_access_key_id=access, aws_secret_access_key=secret,
                        region_name='auto', config=Config(signature_version='s3v4',
                            connect_timeout=2, read_timeout=2,
                            retries={'total_max_attempts': 1, 'mode': 'standard'}))


def _store():
    from monitor.pulse_control import PulseControlUnavailable

    account = getattr(settings, 'R2_ACCOUNT_ID', '')
    access = getattr(settings, 'R2_ACCESS_KEY_ID', '')
    secret = getattr(settings, 'R2_SECRET_ACCESS_KEY', '')
    bucket = getattr(settings, 'PULSE_CONTROL_R2_BUCKET', '')
    key = getattr(settings, 'PULSE_CONTROL_R2_KEY', 'pulse/control-v1.json')
    if (not all((account, access, secret, bucket, key)) or not re.fullmatch(r'[a-fA-F0-9]{32}', account)
            or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket)
            or not key.startswith('pulse/') or '..' in key.split('/')):
        raise PulseControlUnavailable('control_remote_unconfigured')
    try:
        client = _client(account, access, secret)
    except (ValueError, BotoCoreError) as exc:
        raise PulseControlUnavailable('control_remote_unavailable') from exc
    return client, bucket, key


def read():
    from monitor.pulse_control import MAX_FILE_BYTES, PulseControlUnavailable, _validate

    client, bucket, key = _store()
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        stream = response['Body']
        try:
            body = stream.read(MAX_FILE_BYTES + 1)
        finally:
            stream.close()
        if len(body) > MAX_FILE_BYTES:
            raise ValueError('oversized_control_file')
        return _validate(json.loads(body)), response['ETag']
    except (BotoCoreError, ClientError, KeyError, OSError, ValueError, TypeError, RecursionError) as exc:
        raise PulseControlUnavailable('control_remote_unavailable_or_invalid') from exc


def _put(row, *, etag=None, create=False):
    from monitor.pulse_control import (
        MAX_FILE_BYTES,
        PulseControlConflict,
        PulseControlUnavailable,
        _validate,
    )

    body = json.dumps(_validate(row), ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    if len(body) > MAX_FILE_BYTES:
        raise PulseControlUnavailable('control_remote_oversized')
    client, bucket, key = _store()
    condition = {'IfNoneMatch': '*'} if create else {'IfMatch': etag}
    try:
        client.put_object(Bucket=bucket, Key=key, Body=body, ContentType='application/json',
                          CacheControl='private, no-store', **condition)
    except ClientError as exc:
        if exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 412:
            raise PulseControlConflict('control_revision_changed') from exc
        raise PulseControlUnavailable('control_remote_unavailable') from exc
    except (BotoCoreError, OSError) as exc:
        raise PulseControlUnavailable('control_remote_unavailable') from exc


def initialize(row):
    _put(row, create=True)
    return row


def update(change):
    """Compare-and-swap the whole document, retaining concurrent diagnostics."""
    from monitor.pulse_control import PulseControlConflict

    for _ in range(3):
        row, etag = read()
        changed = change(row)
        if changed is False:
            return row
        try:
            _put(row, etag=etag)
            return row
        except PulseControlConflict:
            continue
    raise PulseControlConflict('control_concurrent_updates')

"""Strict identity and byte checks for a Graphics still before publication."""

import hashlib
import re
from io import BytesIO

from django.core.files.storage import storages
from PIL import Image, UnidentifiedImageError

from core.models import ContentPicture, OriginalContentCall
from monitor.original_content import WORKFLOWS, digest

PROVENANCE_FIELDS = frozenset({'schema_version', 'role', 'candidate_id', 'mime', 'producer_call_id', 'content_id'})
MAX_STILL_BYTES = 32 * 1024 * 1024
MIME_FORMATS = {'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WEBP'}
VIDEO_JOB_FIELDS = frozenset({
    'schema_version', 'candidate_id', 'content_id', 'producer_call_id',
    'input_still_sha256', 'terminal_status',
})
VIDEO_TERMINAL_FAILURES = frozenset({'failed', 'expired', 'canceled', 'cancelled', 'moderated'})


def validate_still(picture, *, content, candidate, storage=None):
    """Verify saved file, owning run/content and completed matching image call.

    The exact source inputs remain on the immutable producing call/source rows;
    this small versioned record describes the generated file itself.
    """
    metadata = picture.provenance
    if not isinstance(metadata, dict) or set(metadata) != PROVENANCE_FIELDS:
        raise ValueError('invalid Graphics artifact provenance')
    if (
        metadata['schema_version'] != 'graphics-artifact/v1'
        or metadata['role'] != 'still'
        or metadata['candidate_id'] != candidate
        or candidate not in {'A', 'B'}
        or metadata['content_id'] != str(content.pk)
        or metadata['mime'] not in MIME_FORMATS
        or type(metadata['producer_call_id']) is not int
        or picture.run_id != content.run_id
        or picture.state != 'complete'
        or not re.fullmatch(r'[0-9a-f]{64}', picture.generated_sha256 or '')
        or not picture.generated_storage_name
    ):
        raise ValueError('Graphics still identity mismatch')
    call = OriginalContentCall.objects.filter(pk=metadata['producer_call_id']).first()
    stage = 'I-' + candidate
    if (
        call is None or call.run_id != content.run_id
        or call.workflow_key != content.workflow_key or call.kind != 'media'
        or call.state != 'completed'
        or call.request_identity != f'graphics:{content.run_id}:{stage}'
        or call.stage != f'gfx:{content.run_id}:{stage}'
    ):
        raise ValueError('Graphics still producer mismatch')
    storage = storage if storage is not None else storages['editorial_media']
    try:
        with storage.open(picture.generated_storage_name, 'rb') as stream:
            data = stream.read(MAX_STILL_BYTES + 1)
        if not data or len(data) > MAX_STILL_BYTES or hashlib.sha256(data).hexdigest() != picture.generated_sha256:
            raise ValueError('Graphics still bytes mismatch')
        with Image.open(BytesIO(data)) as image:
            if image.format != MIME_FORMATS[metadata['mime']]:
                raise ValueError('Graphics still MIME mismatch')
            image.verify()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError('Graphics still unreadable') from exc
    return metadata


def validate_failed_video_job(job, *, content, primary_text, producer_call, storage=None):
    """Require saved terminal provider evidence for the exact submitted A video."""
    metadata = job.provenance
    track = next((name for name, workflow in WORKFLOWS.items() if workflow == content.workflow_key), None)
    if not isinstance(metadata, dict) or set(metadata) != VIDEO_JOB_FIELDS:
        raise ValueError('invalid Graphics video job evidence')
    response = producer_call.response_payload
    if (
        metadata['schema_version'] != 'graphics-video-job/v1'
        or metadata['candidate_id'] != 'A'
        or metadata['content_id'] != str(content.pk)
        or type(metadata['producer_call_id']) is not int
        or metadata['producer_call_id'] != producer_call.pk
        or metadata['terminal_status'] not in VIDEO_TERMINAL_FAILURES
        or not isinstance(metadata['input_still_sha256'], str)
        or not re.fullmatch(r'[0-9a-f]{64}', metadata['input_still_sha256'])
        or job.run_id != content.run_id
        or job.text_id != primary_text.pk
        or job.content_kind != track
        or job.content_id != str(primary_text.public_id)
        or job.state != 'failed'
        or type(job.poll_count) is not int or job.poll_count < 1
        or not isinstance(job.provider_task_id, str)
        or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', job.provider_task_id)
        or not isinstance(response, dict)
        or response.get('request_id') != job.provider_task_id
        or producer_call.response_hash != digest(response)
    ):
        raise ValueError('invalid Graphics video job identity')
    stills = ContentPicture.objects.filter(
        text_id=primary_text.pk, run_id=content.run_id,
        content_kind=track, content_id=str(primary_text.public_id),
        generated_sha256=metadata['input_still_sha256'], state='complete',
    )
    matches = 0
    for still in stills:
        try:
            validate_still(still, content=content, candidate='A', storage=storage)
        except (ValueError, TypeError, KeyError):
            continue
        matches += 1
    if matches != 1:
        raise ValueError('Graphics video job input still mismatch')
    return metadata

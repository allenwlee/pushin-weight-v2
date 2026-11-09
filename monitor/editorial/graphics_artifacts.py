"""Strict identity and byte checks for a Graphics still before publication."""

import hashlib
import re
from io import BytesIO

from django.core.files.storage import storages
from PIL import Image, UnidentifiedImageError

from core.models import OriginalContentCall

PROVENANCE_FIELDS = frozenset({'schema_version', 'role', 'candidate_id', 'mime', 'producer_call_id', 'content_id'})
MAX_STILL_BYTES = 32 * 1024 * 1024
MIME_FORMATS = {'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WEBP'}


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

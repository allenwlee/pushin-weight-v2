"""Select one reviewed product from retained captures through the shared writer."""
from copy import deepcopy
from uuid import UUID

from core.benchmark_metric_store import native_date, persist_source
from core.data_source_backfill_cohort import END, IDENTIFIERS, START, campaign_specifications
from core.data_source_backfill_target import isolated_backfill_review
from core.measurement_taxonomy import digest, require

ORIGIN_RESOURCE = 'dpg-d9koekqjobas73fvjqng-a'


def select_retained_payload(source, payload):
    require(source in {'hf', 'arena', 'openrouter'}, 'unsupported retained 0813 source')
    require(isinstance(payload, dict) and payload.get('status') in {'ok', 'partial'}
            and isinstance(payload.get('rows'), list) and len(payload['rows']) <= 25000,
            'bounded retained payload required')
    selected = deepcopy(payload)
    selected['rows'] = []
    lower, upper = native_date(START[:10]), native_date(END[:10])
    for row in payload['rows']:
        field = {'hf': 'repo_id', 'arena': 'model_name', 'openrouter': 'model_permaslug'}[source]
        identifier = row.get(field)
        match = (identifier.casefold() == IDENTIFIERS[source].casefold()
                 if source == 'hf' and isinstance(identifier, str) else identifier == IDENTIFIERS[source])
        if not match:
            continue
        day = row.get('_source_metadata', {}).get('archive_snapshot_date') if source == 'hf' else row.get(
            'leaderboard_publish_date' if source == 'arena' else 'date')
        require(day is not None, 'retained 0813 row has no explicit historical day')
        if lower <= native_date(day) < upper:
            require(source != 'arena' or row.get('category') == 'overall' and payload.get('config') == 'text',
                    'retained Arena variant/category changed')
            selected['rows'].append(deepcopy(row))
    return selected


def reuse_capture(contract, *, source, payload, origin):
    """Keep origin hashes/clocks; IDs from production are provenance, never FKs."""
    require(set(origin) == {'resource', 'run_id', 'archive_id', 'payload_sha256'}
            and origin.get('resource') == ORIGIN_RESOURCE
            and origin.get('payload_sha256') == digest(payload), 'retained capture origin/hash mismatch')
    for field in ('run_id', 'archive_id'):
        require(str(UUID(origin[field])) == origin[field], 'invalid retained origin identity')
    # Validate all four provider pins before admitting even one selected source.
    campaign_specifications(contract)
    selected = select_retained_payload(source, payload)
    require(bool(selected['rows']), 'retained capture contains no requested 0813 observations')
    metadata = {'ingestion_mode': 'historical_import', 'retained_capture_origin': dict(origin),
        'selection': {'identifier': IDENTIFIERS[source], 'start_at': START, 'end_at': END},
        'secondary_source': source == 'hf'}
    key = digest(['0813-retained-capture-v1', contract.contract_hash, source, origin, digest(selected)])
    with isolated_backfill_review():
        return persist_source(contract, source, key, selected, source_metadata=metadata)


def prepare_retained_replay(run_id):
    """Read and verify one bounded committed selection, with no writes or HTTP."""
    from core.collection_capture import read_document
    from core.models import CollectionEvidenceArchive, CollectionRun

    run = CollectionRun.objects.select_related('job__contract').get(pk=UUID(str(run_id)))
    require(run.completed_at is not None and run.status in {'success', 'partial'}
            and run.payload_archive_id and run.source_metadata_archive_id,
            'completed retained capture required')
    contract, source = run.job.contract, run.job.source_id
    campaign_specifications(contract)
    payload_archive = CollectionEvidenceArchive.objects.only('pk', 'byte_count').get(pk=run.payload_archive_id)
    metadata_archive = CollectionEvidenceArchive.objects.only('pk', 'byte_count').get(pk=run.source_metadata_archive_id)
    require(payload_archive.byte_count <= 25 * 1024**2 and metadata_archive.byte_count <= 64 * 1024,
            'retained replay byte cap')
    payload, metadata = read_document(payload_archive), read_document(metadata_archive)
    origin = metadata.get('retained_capture_origin')
    require(isinstance(origin, dict) and origin.get('resource') == ORIGIN_RESOURCE
            and digest(payload) == run.payload_sha256
            and select_retained_payload(source, payload) == payload
            and run.ingestion_key == digest(['0813-retained-capture-v1',
                contract.contract_hash, source, origin, digest(payload)]),
            'retained replay identity or payload changed')
    return run, contract, source, payload, metadata


def replay_retained_run(run_id):
    """Replay the committed selection without its original transport file."""
    with isolated_backfill_review():
        run, contract, source, payload, metadata = prepare_retained_replay(run_id)
        return persist_source(contract, source, run.ingestion_key, payload, source_metadata=metadata)

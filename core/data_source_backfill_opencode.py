"""Finite OpenCode history uses the existing typed metric operation and targets."""
from copy import deepcopy
from datetime import timedelta

from core.measurement_taxonomy import require


def is_opencode_history(job):
    return (job.source_id, job.purpose, job.operation, job.mode) == (
        'opencode', 'metric', 'collect_metrics', 'historical')


def history_window(job):
    """Return inclusive provider days from sealed UTC [start,end) target bounds."""
    require(is_opencode_history(job) and job.instruction_version == 2,
            'OpenCode history requires typed historical metric instructions')
    targets = list(job.targets.select_related('mapping__subject', 'subject'))
    return validate_history_targets(job.contract, targets)


def validate_history_targets(contract, targets):
    require(0 < len(targets) <= 100, 'OpenCode history requires a bounded selection')
    bounds, mappings = set(), set()
    for target in targets:
        mapping = target.mapping
        require(target.target_kind == 'metric_subject' and target.target_role == 'history'
                and target.resolution_state == 'resolved' and mapping is not None
                and mapping.source_id == 'opencode' and mapping.purpose == 'metric'
                and mapping.subject_id == target.subject_id
                and target.subject.subject_kind == 'product'
                and target.native_identifier == mapping.external_identifier,
                'OpenCode history target differs from reviewed metric identity')
        start, end = target.requested_start_at, target.requested_end_at
        require(start is not None and end is not None
                and start.utcoffset() == end.utcoffset() == timedelta(0)
                and start.time().isoformat() == end.time().isoformat() == '00:00:00'
                and 0 < (end - start).days <= 366,
                'OpenCode history requires whole explicit UTC days and exclusive end')
        bounds.add((start, end))
        mappings.add(mapping.pk)
    require(len(bounds) == 1 and len(mappings) == len(targets)
            and mappings == set(contract.mappings.filter(
        source_id='opencode', purpose='metric').values_list('pk', flat=True)),
        'OpenCode history contract and target cohort differ')
    start, end = bounds.pop()
    return start.date().isoformat(), (end.date() - timedelta(days=1)).isoformat()


def preview_history_targets(contract, targets):
    from core.collection_instructions import TARGET_FIELDS, _normalize_references
    from core.models import CollectionJobTarget

    require(isinstance(targets, list) and 0 < len(targets) <= 100,
            'OpenCode history requires a bounded selection')
    require(all(isinstance(target, dict) and set(target) <= set(TARGET_FIELDS)
                for target in targets), 'unsupported OpenCode history target field')
    return validate_history_targets(contract, [CollectionJobTarget(**_normalize_references(
        CollectionJobTarget, target)) for target in targets])


def replay_history(job):
    from core.benchmark_metric_store import persist_source
    from core.collection_capture import read_document
    from core.measurement_taxonomy import digest
    from core.models import CollectionEvidenceArchive

    history_window(job)
    run = job.last_attempt
    require(run is not None and run.completed_at is not None and run.payload_archive_id is not None,
            'completed bounded OpenCode capture required for replay')
    archive = CollectionEvidenceArchive.objects.only('pk', 'byte_count').get(pk=run.payload_archive_id)
    require(archive.byte_count <= job.budgets['bytes'], 'OpenCode replay payload byte cap')
    payload = read_document(archive)
    require(digest(payload) == run.payload_sha256, 'OpenCode replay payload changed')
    return persist_source(job.contract, 'opencode', run.ingestion_key, payload=payload)


def select_history_window(payload, start, end):
    """Select unchanged reported dates; original wire evidence stays captured."""
    from core.benchmark_metric_timing import native_date

    lower, upper = native_date(start), native_date(end)
    require(0 <= (upper - lower).days < 366, 'OpenCode history date cap')
    selected = deepcopy(payload)
    rows = selected['rows']
    selected['rows'] = [row for row in rows if row.get('status') == 'error'
                        or lower <= native_date(row['date']) <= upper]
    for check in selected['endpoint_checks']:
        if check.get('status') != 'ok':
            continue
        identifier = check['source_identifier']
        dates = sorted(row['date'] for row in selected['rows']
                       if row.get('status') != 'error' and row['model_id'] == identifier)
        # The wire capture retains every source date, including an outlier year.
        # This is a selected-row revision marker, not rewritten provider bytes.
        check['dates'] = dates
        if not dates:
            check.update(status='error', error_code='requested_history_unavailable')
            selected['rows'].append({'model_id': identifier, 'status': 'error',
                'error_code': 'requested_history_unavailable',
                '_source_metadata': {'endpoint_path': check['endpoint_path']}})
    if any(check.get('status') != 'ok' for check in selected['endpoint_checks']):
        selected['status'] = 'partial'
    selected['coverage'] = 'requested_model_history'
    return selected

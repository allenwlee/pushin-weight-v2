"""Move the reviewed 0813 backfill measurements into another database by replay.

Integer IDs differ between databases, so rows are never copied. The backfill
side exports its reviewed source captures and the exact values they produced.
The target rebuilds the contract from the same reviewed specification, replays
every capture through the shared writer, and commits only when each resulting
value, observation and reader point equals the exported original.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from django.db import connection, transaction

from core.benchmark_metric_store import aware_instant, native_date, persist_source
from core.data_source_backfill_cohort import (
    END,
    IDENTIFIERS,
    PRODUCT,
    PUBLISHER,
    START,
    campaign_specifications,
    cohort_collection_spec,
)
from core.data_source_backfill_reuse import ORIGIN_RESOURCE, select_retained_payload
from core.data_source_backfill_target import DATABASE as BACKFILL_DATABASE
from core.data_source_backfill_target import RESOURCE as BACKFILL_RESOURCE
from core.measurement_taxonomy import digest, require

FORMAT = 'backfill-contract-transfer-v1'
SOURCES = ('arena', 'hf', 'openrouter', 'opencode')
MAX_CAPTURES = 100
MAX_PAYLOAD_BYTES = 64 * 1024
# Clocks and database-local references; every other stored field must agree.
LOCAL_OBSERVATION_FIELDS = frozenset({
    'id', 'run', 'scope_run', 'observed_at', 'updated_at', 'mapping', 'request',
    'legacy_archive', 'supersedes_observation', 'post', 'source_dataset', 'product',
})
LOCAL_VALUE_FIELDS = frozenset({'id', 'observation', 'source_metric', 'window_range'})


def _plain(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        return bytes(value).hex()
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    raise TypeError(f'unsupported stored value {type(value).__name__}')


def requested_days():
    first, stop = native_date(START[:10]), native_date(END[:10])
    return [(first + timedelta(days=offset)).isoformat() for offset in range((stop - first).days)]


def bundle_digest(bundle):
    return digest({key: value for key, value in bundle.items() if key != 'bundle_sha256'})


def _definition_identity(snapshot):
    return {key: value for key, value in snapshot.items() if key != 'id'}


def _definitions(contract):
    return {source: sorted((_definition_identity(row) for row in settings['definitions']),
                           key=lambda row: (row['metric_key'], row['version']))
            for source, settings in sorted(contract.source_configuration.items())}


def _metric_runs(contract):
    from core.models import CollectionRun

    return list(CollectionRun.objects.filter(job__contract=contract, job__purpose='metric')
                .select_related('job', 'payload_archive', 'source_metadata_archive')
                .order_by('completed_at', 'pk'))


def observation_record(observation):
    from core.models import CollectionObservation

    record = {}
    for field in CollectionObservation._meta.concrete_fields:
        if field.name not in LOCAL_OBSERVATION_FIELDS:
            record[field.name] = _plain(getattr(observation, field.attname))
    record['mapping_identifier'] = observation.mapping.external_identifier if observation.mapping_id else None
    record['source_dataset'] = observation.source_dataset.code if observation.source_dataset_id else None
    record['product_key'] = str(observation.product.product_key) if observation.product_id else None
    return record


def value_record(value):
    from core.models import MetricValue

    record = {}
    for field in MetricValue._meta.concrete_fields:
        if field.name not in LOCAL_VALUE_FIELDS:
            record[field.name] = _plain(getattr(value, field.attname))
    record['observation_key'] = value.observation.observation_key
    record['metric_key'] = value.source_metric.metric_key
    record['metric_version'] = value.source_metric.version
    return record


def run_records(run):
    from core.models import CollectionObservation, MetricValue

    observations = [observation_record(observation) for observation in
                    CollectionObservation.objects.filter(run=run)
                    .select_related('mapping', 'source_dataset', 'product').order_by('observation_key')]
    values = [value_record(value) for value in
              MetricValue.objects.filter(observation__run=run)
              .select_related('observation', 'source_metric')
              .order_by('observation__observation_key', 'source_metric__metric_key', 'source_metric__version')]
    return observations, values


def reader_points(contract):
    """What the shared chart reader returns for every pinned single-product line."""
    from core.benchmark_metric_series import metric_points

    subject = str(contract.mappings.values_list('subject_id', flat=True).first())
    days = requested_days()
    result = {}
    for source in SOURCES:
        if source not in contract.source_configuration:
            continue
        for metric in sorted(contract.source_configuration[source]['metrics']):
            line = {'source': source, 'metric_key': metric, 'subject_id': subject,
                    'mapping_identifiers': [IDENTIFIERS[source]]}
            points, _, _ = metric_points(contract, line, days)
            result[f'{source}:{metric}'] = [
                {'date': point['date'], 'raw_value': point.get('raw_value'),
                 'coverage': point.get('coverage'), 'observed': point.get('observed', True)}
                for point in points]
    return result


def observed_points(points):
    return {line: sorted((point['date'], point['raw_value']) for point in rows
                         if point['raw_value'] is not None and point['observed'] is not False)
            for line, rows in points.items()}


def build_bundle(contract):
    """Export reviewed captures and their values; reads only."""
    from core.collection_capture import read_document

    campaign_specifications(contract)
    require(contract.methodology.get('local_product_type_review') == 'llm-model'
            and contract.methodology.get('backfill_reference_sha256'), 'reviewed 0813 methodology required')
    mappings = {m.source_id: m for m in contract.mappings.select_related('identifier_scope')}
    captures = []
    for ordinal, run in enumerate(_metric_runs(contract)):
        require(run.status == 'success' and run.completed_at is not None, 'only successful captures transfer')
        require(run.payload_archive_id and run.source_metadata_archive_id, 'capture evidence missing')
        payload, metadata = read_document(run.payload_archive), read_document(run.source_metadata_archive)
        require(digest(payload) == run.payload_sha256, 'capture payload hash mismatch')
        require(run.payload_archive.byte_count <= MAX_PAYLOAD_BYTES, 'capture exceeds transfer size')
        observations, values = run_records(run)
        captures.append({
            'ordinal': ordinal, 'source': run.job.source_id, 'status': run.status,
            'origin_run_id': str(run.pk), 'origin_ingestion_key': run.ingestion_key,
            'origin_completed_at': run.completed_at.isoformat(),
            'payload_sha256': run.payload_sha256, 'payload': payload, 'source_metadata': metadata,
            'expected_observations': observations, 'expected_values': values,
        })
    require(0 < len(captures) <= MAX_CAPTURES, 'capture count outside transfer bounds')
    bundle = {
        'format': FORMAT,
        'origin': {
            'resource': BACKFILL_RESOURCE, 'database': connection.settings_dict.get('NAME'),
            'contract_id': str(contract.pk), 'contract_hash': contract.contract_hash,
            'catalog_hash': contract.catalog_hash, 'mapping_hash': contract.mapping_hash,
            'methodology_hash': contract.methodology_hash, 'methodology': contract.methodology,
            'catalog_snapshot': contract.catalog_snapshot,
            'subject_id': str(mappings['hf'].subject_id), 'product_key': PRODUCT,
            'archive_row_key': mappings['hf'].identifier_metadata['archive_row_key'],
            'mappings': {source: {'external_identifier': m.external_identifier,
                                  'source_subject_kind': m.source_subject_kind,
                                  'identifier_scope': m.identifier_scope_code,
                                  'mapping_hash': m.mapping_hash}
                         for source, m in sorted(mappings.items())},
            'definitions': _definitions(contract),
        },
        'captures': captures,
        'expected_reader': reader_points(contract),
        'value_count': sum(len(capture['expected_values']) for capture in captures),
    }
    bundle['bundle_sha256'] = bundle_digest(bundle)
    return bundle


def validate_bundle(bundle):
    require(isinstance(bundle, dict) and bundle.get('format') == FORMAT, 'unknown transfer bundle')
    require(bundle.get('bundle_sha256') == bundle_digest(bundle), 'transfer bundle hash mismatch')
    origin = bundle['origin']
    require(origin['resource'] == BACKFILL_RESOURCE and origin['product_key'] == PRODUCT,
            'transfer bundle has another origin')
    captures = bundle['captures']
    require(0 < len(captures) <= MAX_CAPTURES
            and [capture['ordinal'] for capture in captures] == list(range(len(captures))),
            'transfer captures are incomplete or reordered')
    for capture in captures:
        require(capture['source'] in SOURCES and capture['status'] == 'success',
                'unsupported transfer capture')
        require(digest(capture['payload']) == capture['payload_sha256'], 'capture payload hash mismatch')
    require(bundle['value_count'] == sum(len(c['expected_values']) for c in captures),
            'transfer value count mismatch')


def _require_target(expected_database):
    from core.data_source_backfill_target import _backfill_host

    settings = connection.settings_dict
    require(bool(expected_database) and expected_database != BACKFILL_DATABASE,
            'explicit non-backfill target database required')
    require(not _backfill_host(settings.get('HOST')), 'transfer target is the backfill database')
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        actual = cursor.fetchone()[0]
    require(actual == expected_database, 'connected database differs from the requested target')
    return actual


def _prepare_product():
    """Record the reviewed product type on the exact 0813 record; refuse other identities."""
    from core.models import Product
    from core.product_vocabulary import product_type_id

    product = Product.objects.select_for_update().get(product_key=PRODUCT)
    require(product.repo_id == IDENTIFIERS['hf'] and product.brand_id == 'deepseek'
            and product.hf_type == 'model' and str(product.publisher_account_id) == PUBLISHER
            and product.private is False and product.disabled is not True
            and product.created_at == aware_instant('2026-08-13T03:05:06Z'),
            '0813 product identity differs from the reviewed cohort')
    before = product.product_type_code
    require(before in (None, 'llm-model'), '0813 product already has another reviewed type')
    if before is None:
        product.product_type_id = product_type_id('llm-model')
        product.save(update_fields=['product_type'])
    return before


def _verify_retained_origin(capture):
    """A capture copied from this database must still match its original evidence."""
    from core.collection_capture import read_document
    from core.models import CollectionRun

    origin = capture['source_metadata'].get('retained_capture_origin')
    if not origin or origin.get('resource') != ORIGIN_RESOURCE:
        return False
    run = CollectionRun.objects.select_related('payload_archive').filter(pk=origin['run_id']).first()
    require(run is not None and str(run.payload_archive_id) == origin['archive_id']
            and run.payload_sha256 == origin['payload_sha256'],
            'retained origin capture is missing or changed')
    require(select_retained_payload(capture['source'], read_document(run.payload_archive))
            == capture['payload'], 'retained origin no longer selects the transferred rows')
    return True


def _compare(expected, actual, key_fields):
    def index(rows):
        return {tuple(row[field] for field in key_fields): row for row in rows}

    left, right = index(expected), index(actual)
    problems = []
    for key in sorted(left.keys() | right.keys(), key=str):
        if key not in right:
            problems.append({'key': list(key), 'problem': 'missing'})
        elif key not in left:
            problems.append({'key': list(key), 'problem': 'unexpected'})
        else:
            fields = sorted(name for name in left[key].keys() | right[key].keys()
                            if left[key].get(name) != right[key].get(name))
            if fields:
                problems.append({'key': list(key), 'problem': 'differs', 'fields': {
                    name: {'expected': left[key].get(name), 'actual': right[key].get(name)}
                    for name in fields}})
    return problems


def _cell_day(source, observation, value):
    if source == 'hf':
        return (observation.archive_snapshot_date or observation.reconstruction_date
                or observation.observed_at.date())
    return value.as_of_date or value.period_label_date


def classify_cells(expected, existing):
    """expected: {cell: {numbers}}; existing: {cell: [(contract_id, number), ...]}.

    A cell is equivalent only when every existing measurement equals the one
    transferred number; transferred captures that disagree are reported, never
    silently resolved.
    """
    rows = []
    for cell in sorted(expected):
        numbers, others = sorted(expected[cell]), existing.get(cell, [])
        if len(numbers) > 1:
            state = 'transferred_captures_disagree'
        elif not others:
            state = 'inserted_only'
        elif all(number == numbers[0] for _, number in others):
            state = 'equivalent'
        else:
            state = 'conflicting'
        rows.append({'source': cell[0], 'metric_key': cell[1], 'date': cell[2],
                     'transferred_values': numbers, 'state': state,
                     'existing': [{'contract_id': contract, 'value': number} for contract, number in others]})
    return rows


def reconcile_existing(bundle):
    """Compare each transferred cell with measurements held outside any copy of this contract.

    Read-only; it runs before the write transaction so its scans hold no locks.
    """
    from core.models import MetricValue

    expected = {}
    for capture in bundle['captures']:
        observations = {row['observation_key']: row for row in capture['expected_observations']}
        for row in capture['expected_values']:
            observation = observations[row['observation_key']]
            if capture['source'] == 'hf':
                day = (observation['archive_snapshot_date'] or observation['reconstruction_date'])
            else:
                day = row['as_of_date'] or row['period_label_date']
            number = row['integer_value'] if row['integer_value'] is not None else row['float_value']
            expected.setdefault((capture['source'], row['metric_key'], day), set()).add(number)
    existing = {}
    for source in sorted({cell[0] for cell in expected}):
        identifier = IDENTIFIERS[source]
        queryset = (MetricValue.objects.filter(observation__run__job__source_id=source, observation__status='ok')
                    .exclude(observation__run__job__contract__mapping_hash=bundle['origin']['mapping_hash'],
                             observation__run__job__contract__methodology_hash=bundle['origin']['methodology_hash'])
                    .select_related('observation__run__job', 'source_metric'))
        queryset = (queryset.filter(observation__source_identifier__iexact=identifier) if source == 'hf'
                    else queryset.filter(observation__source_identifier=identifier))
        for value in queryset:
            day = _cell_day(source, value.observation, value)
            cell = (source, value.source_metric.metric_key, day.isoformat() if day else None)
            if cell in expected:
                number = (_plain(value.integer_value) if value.integer_value is not None
                          else _plain(value.float_value))
                existing.setdefault(cell, []).append((str(value.observation.run.job.contract_id), number))
    rows = classify_cells(expected, existing)
    summary = {}
    for row in rows:
        summary[row['state']] = summary.get(row['state'], 0) + 1
    missing = {source: [day for day in requested_days()
                        if not any(cell[0] == source and cell[2] == day for cell in expected)]
               for source in sorted({cell[0] for cell in expected})}
    return {'cells': len(rows), 'summary': summary, 'missing_requested_days': missing,
            'details': [row for row in rows if row['state'] != 'inserted_only']}


class _Rollback(Exception):
    def __init__(self, report):
        super().__init__('transfer rolled back')
        self.report = report


def _transfer(bundle, *, reviewed_by, database):
    from core.benchmark_metric_identity import configure_collection
    from core.measurement_taxonomy import configure_taxonomy, resolve_subject_id
    from core.models import CollectionRun, MetricCollectionContract

    origin = bundle['origin']
    product_type_before = _prepare_product()
    taxonomy = configure_taxonomy({'reviewed_by': reviewed_by, 'subjects': [{'kind': 'product', 'key': PRODUCT}]})
    subject = str(resolve_subject_id('product', PRODUCT))
    require(subject == origin['subject_id'] and taxonomy.snapshot == origin['catalog_snapshot'],
            'target catalog differs from the reviewed backfill catalog')
    spec = cohort_collection_spec(taxonomy_id=taxonomy.pk, subject_id=subject, reviewed_by=reviewed_by,
                                  archive_row_key=origin['archive_row_key'],
                                  reference_sha256=origin['methodology']['backfill_reference_sha256'],
                                  product_type_review=origin['methodology']['local_product_type_review'])
    require(spec['methodology'] == origin['methodology'], 'transfer methodology differs')
    existing_contracts = set(MetricCollectionContract.objects.values_list('pk', flat=True))
    contract = configure_collection(spec)
    require((contract.catalog_hash, contract.mapping_hash, contract.methodology_hash)
            == (origin['catalog_hash'], origin['mapping_hash'], origin['methodology_hash']),
            'target contract identity differs from the backfill contract')
    require(_definitions(contract) == origin['definitions'], 'target metric definitions differ')
    created = 0
    problems = []
    for capture in bundle['captures']:
        key = digest([FORMAT, contract.contract_hash, capture['origin_run_id'], capture['payload_sha256']])
        existed = CollectionRun.objects.filter(ingestion_key=key).exists()
        metadata = {**capture['source_metadata'], 'backfill_transfer_origin': {
            'resource': origin['resource'], 'contract_id': origin['contract_id'],
            'contract_hash': origin['contract_hash'], 'run_id': capture['origin_run_id'],
            'ingestion_key': capture['origin_ingestion_key'], 'payload_sha256': capture['payload_sha256'],
            'bundle_sha256': bundle['bundle_sha256']}}
        run = persist_source(contract, capture['source'], key, capture['payload'], source_metadata=metadata)
        created += not existed
        if run.status != capture['status'] or run.payload_sha256 != capture['payload_sha256']:
            problems.append({'capture': capture['ordinal'], 'problem': 'replay status or payload differs',
                             'status': run.status, 'error_code': run.error_code})
            continue
        observations, values = run_records(run)
        problems += [{'capture': capture['ordinal'], 'record': 'observation', **problem} for problem in
                     _compare(capture['expected_observations'], observations, ('observation_key',))]
        problems += [{'capture': capture['ordinal'], 'record': 'value', **problem} for problem in
                     _compare(capture['expected_values'], values,
                              ('observation_key', 'metric_key', 'metric_version'))]
    expected_reader, actual_reader = bundle['expected_reader'], reader_points(contract)
    if observed_points(expected_reader) != observed_points(actual_reader):
        problems.append({'record': 'reader', 'problem': 'observed reader points differ',
                         'expected': observed_points(expected_reader), 'actual': observed_points(actual_reader)})
    # Unobserved days may be labelled differently when the target knows more
    # Arena publication dates; observed values above must still be identical.
    label_changes = [
        {'line': line, 'date': exp['date'], 'expected': exp['coverage'], 'actual': act['coverage']}
        for line in sorted(expected_reader)
        for exp, act in zip(expected_reader[line], actual_reader.get(line, []), strict=False)
        if exp['raw_value'] is None and act['raw_value'] is None and exp['coverage'] != act['coverage']]
    from core.models import MetricValue

    values = MetricValue.objects.filter(observation__run__job__contract=contract).count()
    if values != bundle['value_count']:
        problems.append({'record': 'contract', 'problem': 'value count differs',
                         'expected': bundle['value_count'], 'actual': values})
    return {
        'database': database, 'bundle_sha256': bundle['bundle_sha256'],
        'origin_contract': {'id': origin['contract_id'], 'hash': origin['contract_hash']},
        'contract': {'id': str(contract.pk), 'hash': contract.contract_hash,
                     'created': contract.pk not in existing_contracts,
                     'catalog_hash': contract.catalog_hash, 'mapping_hash': contract.mapping_hash,
                     'methodology_hash': contract.methodology_hash, 'taxonomy_version': str(taxonomy.pk)},
        'product_type_before': product_type_before, 'product_type_after': 'llm-model',
        'captures': len(bundle['captures']), 'captures_created': created,
        'values': values,
        'reader_lines': len(actual_reader),
        'reader_observed_points': sum(len(rows) for rows in observed_points(actual_reader).values()),
        'reader_label_differences': label_changes,
        'problems': problems,
    }


def apply_bundle(bundle, *, expected_database, reviewed_by, commit=False):
    """Replay inside one transaction; keep it only if commit is requested and nothing differs."""
    require(bool(reviewed_by.strip()), 'transfer reviewer required')
    validate_bundle(bundle)
    database = _require_target(expected_database)
    # Read-only evidence checks first, so the write transaction stays short.
    checks = {'retained_origins_verified': sum(_verify_retained_origin(c) for c in bundle['captures']),
              'reconciliation': reconcile_existing(bundle)}
    try:
        with transaction.atomic():
            report = {**_transfer(bundle, reviewed_by=reviewed_by, database=database), **checks}
            if report['problems'] or not commit:
                raise _Rollback(report)
    except _Rollback as rolled_back:
        return {**rolled_back.report, 'committed': False}
    return {**report, 'committed': True}

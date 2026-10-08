"""Revision references reuse immutable observations without duplicating values.

Each successful endpoint check records the observation used for every returned
date. A later unchanged export therefore advances publication freshness while
retaining the original evidence. Export time orders reports; retrieval time
controls when this application actually knew them.
"""

import json
import re

from django.db import connection

from core.benchmark_metric_store import aware_instant
from core.measurement_taxonomy import require
from core.models import MetricCollectionRun, MetricObservation


def retained_checks(contract, *, cutoff=None):
    runs = MetricCollectionRun.objects.filter(
        contract=contract, source_id="opencode", status__in=["success", "partial"]
    )
    if cutoff is not None:
        runs = runs.filter(completed_at__lte=cutoff)
    result = []
    for index, run in enumerate(
        runs.only("source_metadata", "completed_at")
        .order_by("-completed_at", "-id")[:10001]
        .iterator(chunk_size=100)
    ):
        require(index < 10000, "OpenCode revision query budget exceeded")
        for check in run.source_metadata.get("endpoint_checks", []):
            if check.get("status") == "ok" and (
                cutoff is None or aware_instant(check["updated_at"]) <= cutoff
            ):
                result.append((run, check))
    return result


def selected_rows(contract, mapping_ids, start, end, *, cutoff=None):
    """Latest reported row per exact model/date, with a stable conflict order."""
    require(0 < len(mapping_ids) <= 100, "OpenCode mapping query budget")
    mappings = dict(
        contract.mappings.filter(pk__in=mapping_ids, source_id="opencode").values_list(
            "external_identifier", "pk"
        )
    )
    # Project requested dates in PostgreSQL rather than loading every hourly
    # report's full reference window into Python memory.
    sql = """
        SELECT DISTINCT ON (check_row.value->>'source_identifier', reference.key)
            check_row.value->>'source_identifier', reference.key,
            reference.value::bigint, r.id,
            check_row.value - 'row_references' - 'dates'
        FROM metric_collection_runs r
        CROSS JOIN LATERAL jsonb_array_elements(COALESCE(r.source_metadata->'endpoint_checks', '[]'::jsonb)) check_row
        CROSS JOIN LATERAL jsonb_each_text(COALESCE(check_row.value->'row_references', '{}'::jsonb)) reference
        WHERE r.contract_id = %s AND r.source_id = 'opencode'
            AND r.status IN ('success', 'partial')
            AND check_row.value->>'status' = 'ok'
            AND check_row.value->>'source_identifier' = ANY(%s)
            AND reference.key BETWEEN %s AND %s
    """
    params = [contract.pk, list(mappings), start, end]
    if cutoff is not None:
        sql += " AND r.completed_at <= %s AND (check_row.value->>'updated_at')::timestamptz <= %s"
        params.extend([cutoff, cutoff])
    sql += " ORDER BY check_row.value->>'source_identifier', reference.key, (check_row.value->>'updated_at')::timestamptz DESC, check_row.value->>'body_sha256' DESC, r.completed_at DESC, r.id DESC LIMIT 36601"
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        selected = cursor.fetchall()
    chosen = {}
    for identifier, label, observation_id, run_id, check in selected:
        check = json.loads(check) if isinstance(check, str) else check
        chosen[(identifier, label)] = {
            "observation_id": observation_id,
            "revision": (aware_instant(check["updated_at"]), check["body_sha256"]),
            "check_run_id": str(run_id),
            "check": check,
        }
    require(len(chosen) <= 36600, "OpenCode selected row budget")
    observations = {
        obj.pk: obj
        for obj in MetricObservation.objects.filter(
            pk__in={row["observation_id"] for row in chosen.values()},
            mapping_id__in=mapping_ids,
            run__contract=contract,
            run__source_id="opencode",
            status="ok",
        )
        .select_related("run")
        .defer("run__raw_payload", "run__request_params")
        .prefetch_related("values__source_metric")
    }
    for (identifier, label), row in chosen.items():
        observation = observations.get(row["observation_id"])
        require(
            observation is not None
            and observation.source_identifier == identifier
            and observation.dimensions.get("date") == label,
            "OpenCode retained reference mismatch",
        )
        row["observation"] = observation
    return chosen


def publication_times(contract):
    """Project one publication instant per model, without materializing hourly windows."""
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT DISTINCT ON (c.value->>'source_identifier')
            c.value->>'source_identifier', (c.value->>'updated_at')::timestamptz
            FROM metric_collection_runs r
            CROSS JOIN LATERAL jsonb_array_elements(COALESCE(r.source_metadata->'endpoint_checks', '[]'::jsonb)) c
            WHERE r.contract_id=%s AND r.source_id='opencode' AND r.status IN ('success','partial')
            AND c.value->>'status'='ok'
            ORDER BY c.value->>'source_identifier', (c.value->>'updated_at')::timestamptz DESC
            LIMIT 101""",
            [contract.pk],
        )
        rows = cursor.fetchall()
    require(len(rows) <= 100, "OpenCode publication cohort budget")
    return dict(rows)


def prepare_revisions(contract, prepared, payload):
    """Compare the entire endpoint window; keep decreased historical corrections."""
    mappings = {
        m.external_identifier: m for m in contract.mappings.filter(source_id="opencode")
    }
    current = selected_rows(
        contract, [m.pk for m in mappings.values()], "0001-01-01", "9999-12-31"
    )
    checks = []
    returned_identifiers = {
        observation["source_identifier"] for observation, _ in prepared
    }
    for native in payload["endpoint_checks"]:
        check = {k: v for k, v in native.items() if k != "native_payload"}
        check["row_references"] = {}
        require(
            check["source_identifier"] in returned_identifiers,
            "OpenCode endpoint outside returned cohort",
        )
        mapping = mappings.get(check["source_identifier"])
        require(
            mapping
            and check["endpoint_path"] == mapping.identifier_metadata["endpoint_path"],
            "OpenCode endpoint differs from reviewed mapping",
        )
        if check.get("status") == "ok":
            aware_instant(check["updated_at"])
            require(
                re.fullmatch(r"[0-9a-f]{64}", check["body_sha256"]),
                "OpenCode endpoint body hash required",
            )
            observations = [
                o
                for o, _ in prepared
                if o["source_identifier"] == check["source_identifier"]
                and o["status"] == "ok"
            ]
            require(
                bool(observations)
                and set(check["dates"])
                == {o["dimensions"]["date"] for o in observations},
                "OpenCode endpoint date references mismatch",
            )
            for observation in observations:
                metadata = observation["source_metadata"]
                require(
                    metadata["updated_at"] == check["updated_at"]
                    and metadata["endpoint_body_sha256"] == check["body_sha256"],
                    "OpenCode endpoint revision metadata mismatch",
                )
                require(
                    metadata["endpoint_path"] == check["endpoint_path"],
                    "OpenCode row endpoint metadata mismatch",
                )
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT EXISTS (
                    SELECT 1 FROM metric_collection_runs r
                    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(r.source_metadata->'endpoint_checks', '[]'::jsonb)) c
                    WHERE r.contract_id=%s AND r.source_id='opencode' AND r.status IN ('success','partial')
                    AND c.value->>'status'='ok' AND c.value->>'source_identifier'=%s
                    AND (c.value->>'updated_at')::timestamptz=%s AND c.value->>'body_sha256'<>%s
                )""",
                    [
                        contract.pk,
                        check["source_identifier"],
                        aware_instant(check["updated_at"]),
                        check["body_sha256"],
                    ],
                )
                if cursor.fetchone()[0]:
                    check["revision_anomaly"] = "same_update_different_body"
        checks.append(check)
    by_identifier = {c["source_identifier"]: c for c in checks}
    require(len(by_identifier) == len(checks), "duplicate OpenCode endpoint check")
    new, successful = [], set()
    for observation, values in prepared:
        if observation["status"] != "ok":
            new.append((observation, values))
            continue
        key = observation["source_identifier"], observation["dimensions"]["date"]
        prior = current.get(key)
        if (
            prior
            and prior["observation"].source_metadata.get("row_semantic_hash")
            == observation["source_metadata"]["row_semantic_hash"]
        ):
            by_identifier[key[0]]["row_references"][key[1]] = prior["observation"].pk
            if observation["mapping"]:
                successful.add(observation["mapping"].pk)
        else:
            new.append((observation, values))
    return new, checks, successful

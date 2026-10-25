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
from core.benchmark_metric_timing import native_date
from core.measurement_taxonomy import digest, require
from core.models import CollectionObservation, CollectionObservationInput, CollectionRun


def record_endpoint_checks(run, checks, contract, *, verify_only=False):
    """Keep successful endpoint revisions and cross-run row references typed."""
    require(run.observed_at is not None, "endpoint observation time required")
    mappings = {
        row.external_identifier: row
        for row in contract.mappings.filter(purpose="metric", source_id="opencode")
    }
    inserted = 0
    for check in checks:
        if check.get("status") != "ok":
            continue
        identifier = check["source_identifier"]
        mapping = mappings.get(identifier)
        require(mapping is not None, "endpoint mapping is missing")
        updated_at = aware_instant(check["updated_at"])
        body_hash = check["body_sha256"]
        require(
            isinstance(body_hash, str) and re.fullmatch(r"[0-9a-f]{64}", body_hash),
            "endpoint body hash is invalid",
        )
        key = digest(["opencode-endpoint-check-v1", str(run.pk), identifier])
        defaults = {
            "mapping": mapping,
            "source_identifier": identifier,
            "source_subject_kind": "model",
            "observed_at": run.observed_at,
            "source_record_at": updated_at,
            "payload_sha256": body_hash,
            "revision_conflict": (
                check.get("revision_anomaly") == "same_update_different_body"
                if "revision_anomaly" in check else None
            ),
            "observation_kind": "endpoint_check",
        }
        if verify_only:
            marker = CollectionObservation.objects.filter(
                run=run, observation_key=key
            ).first()
            require(marker is not None, "endpoint check marker is missing")
        else:
            marker, created = CollectionObservation.objects.get_or_create(
                run=run, observation_key=key, defaults=defaults
            )
            inserted += int(created)
        require(
            all(getattr(marker, field + "_id" if field == "mapping" else field)
                == (value.pk if field == "mapping" else value)
                for field, value in defaults.items()),
            "endpoint check marker conflicts with source evidence",
        )
        for label, observation_id in check.get("row_references", {}).items():
            referenced = CollectionObservation.objects.select_related(
                "run__job"
            ).get(pk=observation_id)
            day = native_date(label)
            require(
                referenced.source_identifier == identifier
                and referenced.run.job.contract_id == contract.pk
                and referenced.run.job.source_id == "opencode"
                and referenced.status == "ok"
                and referenced.mapping_id == mapping.pk
                and referenced.dimensions.get("date") == label,
                "endpoint row reference conflicts with source evidence",
            )
            if referenced.source_record_date is None and not verify_only:
                referenced.source_record_date = day
                referenced.save(update_fields=["source_record_date"])
            require(
                referenced.source_record_date == day,
                "endpoint row date is not typed",
            )
            if verify_only:
                link = CollectionObservationInput.objects.filter(
                    observation=marker,
                    input_observation=referenced,
                    input_role="endpoint_revision_row",
                ).first()
                require(link is not None, "endpoint row link is missing")
            else:
                link, _ = CollectionObservationInput.objects.get_or_create(
                    observation=marker,
                    input_observation=referenced,
                    input_role="endpoint_revision_row",
                    defaults={"row_locator": label},
                )
            require(link.row_locator == label, "endpoint row label conflicts")
    return inserted


def retained_checks(contract, *, cutoff=None):
    runs = CollectionRun.objects.filter(
        job__contract=contract,
        job__source_id="opencode",
        status__in=["success", "partial"],
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


def selected_rows(contract, mapping_ids, start, end, *, cutoff=None, canonical=False):
    """Latest reported row per exact model/date, with a stable conflict order."""
    require(0 < len(mapping_ids) <= 100, "OpenCode mapping query budget")
    mappings = dict(
        contract.mappings.filter(
            purpose="metric", pk__in=mapping_ids, source_id="opencode"
        ).values_list("external_identifier", "pk")
    )
    # Project requested dates in PostgreSQL rather than loading every hourly
    # report's full reference window into Python memory.
    sql = """
        SELECT DISTINCT ON (check_row.value->>'source_identifier', reference.key)
            check_row.value->>'source_identifier', reference.key,
            reference.value::bigint, r.id,
            check_row.value - 'row_references' - 'dates'
        FROM collection_runs r
        JOIN collection_jobs j ON j.id = r.job_id
        CROSS JOIN LATERAL jsonb_array_elements(COALESCE(r.source_metadata->'endpoint_checks', '[]'::jsonb)) check_row
        CROSS JOIN LATERAL jsonb_each_text(COALESCE(check_row.value->'row_references', '{}'::jsonb)) reference
        WHERE j.contract_id = %s AND j.source_id = 'opencode'
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
    if canonical:
        from core.benchmark_serving import selected_endpoint_rows

        selected = selected_endpoint_rows(contract, mapping_ids, start, end, cutoff)
    else:
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
    queryset = CollectionObservation.objects.filter(
        pk__in={row["observation_id"] for row in chosen.values()},
        mapping_id__in=mapping_ids,
        run__job__contract=contract,
        run__job__source_id="opencode",
        status="ok",
    ).select_related("run").defer("run__raw_payload", "run__request_params")
    if canonical:
        queryset = queryset.defer("source_metadata", "run__source_metadata", "run__report")
    observations = {
        obj.pk: obj
        for obj in queryset.prefetch_related("values__source_metric")
    }
    if canonical:
        from core.benchmark_serving import hydrate_observations

        hydrate_observations(observations.values())
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
            """SELECT DISTINCT ON (p.external_identifier)
            p.external_identifier,p.updated_at
            FROM benchmark_endpoint_revisions p JOIN collection_runs r ON r.id=p.run_id
            JOIN collection_jobs j ON j.id=r.job_id
            WHERE j.contract_id=%s
            ORDER BY p.external_identifier,p.updated_at DESC
            LIMIT 101""",
            [contract.pk],
        )
        rows = cursor.fetchall()
    require(len(rows) <= 100, "OpenCode publication cohort budget")
    return dict(rows)


def prepare_revisions(contract, prepared, payload):
    """Compare the entire endpoint window; keep decreased historical corrections."""
    mappings = {
        m.external_identifier: m
        for m in contract.mappings.filter(purpose="metric", source_id="opencode")
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
                    SELECT 1 FROM collection_runs r
        JOIN collection_jobs j ON j.id = r.job_id
                    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(r.source_metadata->'endpoint_checks', '[]'::jsonb)) c
                    WHERE j.contract_id=%s AND j.source_id='opencode' AND r.status IN ('success','partial')
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

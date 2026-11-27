"""Revision references reuse immutable observations without duplicating values.

Each successful endpoint check records the observation used for every returned
date. A later unchanged export therefore advances publication freshness while
retaining the original evidence. Export time orders reports; retrieval time
controls when this application actually knew them.
"""

import re

from django.db import connection

from core.benchmark_metric_store import aware_instant
from core.benchmark_metric_timing import native_date
from core.benchmark_serving import observation_read_fields
from core.measurement_taxonomy import digest, require
from core.models import CollectionObservation, CollectionObservationInput, CollectionRun

REVISION_SOURCES = frozenset({"opencode", "gdpx"})
GDPX_DATASET_IDENTIFIER = "gdpx:dataset"


def revision_identity(source_identifier, category_key, config_key):
    """Observation identity within a contract: model, category and configuration."""
    return "|".join((source_identifier, category_key or "", config_key or ""))


def prepared_identity(observation):
    dimensions = observation["dimensions"]
    return revision_identity(
        observation["source_identifier"],
        dimensions.get("category"),
        dimensions.get("config"),
    )


def stored_identity(observation):
    return revision_identity(
        observation.source_identifier, observation.category_key, observation.config_key
    )


def record_endpoint_checks(run, checks, contract, *, verify_only=False):
    """Keep successful endpoint revisions and cross-run row references typed.

    OpenCode checks belong to one reviewed mapping and reference rows by date.
    GDPx checks cover the link-free dataset and reference rows by observation
    identity (model, category, configuration); no mapping is expected.
    """
    require(run.observed_at is not None, "endpoint observation time required")
    source = run.job.source_id
    require(source in REVISION_SOURCES, "unsupported revision source")
    mappings = {
        row.external_identifier: row
        for row in contract.mappings.filter(purpose="metric", source_id=source)
    }
    inserted = 0
    for check in checks:
        if check.get("status") != "ok":
            continue
        identifier = check["source_identifier"]
        mapping = mappings.get(identifier)
        if source == "opencode":
            require(mapping is not None, "endpoint mapping is missing")
        else:
            require(identifier == GDPX_DATASET_IDENTIFIER, "GDPx check identity mismatch")
        body_hash = check["body_sha256"]
        require(
            isinstance(body_hash, str) and re.fullmatch(r"[0-9a-f]{64}", body_hash),
            "endpoint body hash is invalid",
        )
        key = digest([source + "-endpoint-check-v1", str(run.pk), identifier])
        defaults = {
            "mapping": mapping,
            "source_identifier": identifier,
            "source_subject_kind": "model" if source == "opencode" else "aggregate",
            "observed_at": run.observed_at,
            **(
                {"source_record_at": aware_instant(check["updated_at"])}
                if source == "opencode"
                else {"source_record_date": native_date(check["updated_at"])}
            ),
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
                == (getattr(value, "pk", None) if field == "mapping" else value)
                for field, value in defaults.items()),
            "endpoint check marker conflicts with source evidence",
        )
        for label, observation_id in check.get("row_references", {}).items():
            referenced = CollectionObservation.objects.select_related(
                "run__job"
            ).get(pk=observation_id)
            require(
                referenced.run.job.contract_id == contract.pk
                and referenced.run.job.source_id == source
                and referenced.status == "ok"
                and referenced.mapping_id == getattr(mapping, "pk", None)
                and (
                    referenced.source_identifier == identifier
                    and referenced.source_record_date == native_date(label)
                    if source == "opencode"
                    else stored_identity(referenced) == label
                ),
                "endpoint row reference conflicts with source evidence",
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
    # Bind the operator export to each eligible run before expanding the same
    # security-barrier view used by the chart readers.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT p.run_id,p.external_identifier,p.period_date,p.observation_id,"
            "p.updated_at,p.body_sha256,p.conflicting_revision "
            "FROM collection_jobs j JOIN collection_runs r ON r.job_id=j.id "
            "CROSS JOIN LATERAL (SELECT * FROM benchmark_endpoint_revisions p "
            "WHERE p.run_id=r.id OFFSET 0) p "
            "WHERE j.contract_id=%s AND j.source_id='opencode' "
            "AND j.purpose='metric' AND r.status IN ('success','partial') "
            "AND (%s::timestamptz IS NULL OR (r.completed_at<=%s AND p.updated_at<=%s)) "
            "ORDER BY r.completed_at DESC,r.id DESC,p.external_identifier,p.updated_at "
            "LIMIT 10001",
            [contract.pk, cutoff, cutoff, cutoff],
        )
        rows = cursor.fetchall()
    require(len(rows) <= 10000, "OpenCode revision query budget exceeded")
    runs = CollectionRun.objects.only("completed_at").in_bulk({row[0] for row in rows})
    grouped = {}
    for run_id, identifier, day, observation_id, updated, body_hash, conflict in rows:
        key = (run_id, identifier, updated, body_hash)
        check = grouped.setdefault(
            key,
            {
                "source_identifier": identifier,
                "status": "ok",
                "updated_at": updated.isoformat(),
                "body_sha256": body_hash,
                "row_references": {},
            },
        )
        check["row_references"][day.isoformat()] = observation_id
        if conflict:
            check["revision_anomaly"] = "same_update_different_body"
    return [(runs[run_id], check) for (run_id, _, _, _), check in grouped.items()]


def selected_rows(contract, mapping_ids, start, end, *, cutoff=None, canonical=False):
    """Latest reported row per exact model/date, with a stable conflict order."""
    require(0 < len(mapping_ids) <= 100, "OpenCode mapping query budget")
    from core.benchmark_serving import selected_endpoint_rows

    selected = selected_endpoint_rows(contract, mapping_ids, start, end, cutoff)
    chosen = {}
    for identifier, label, observation_id, run_id, check in selected:
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
    ).select_related("run__job").only(*observation_read_fields())
    observations = {
        obj.pk: obj
        for obj in queryset.prefetch_related("values__source_metric")
    }
    for (identifier, label), row in chosen.items():
        observation = observations.get(row["observation_id"])
        require(
            observation is not None
            and observation.source_identifier == identifier
            and observation.source_record_date
            and observation.source_record_date.isoformat() == label,
            "OpenCode retained reference mismatch",
        )
        row["observation"] = observation
    return chosen


def publication_times(contract):
    """Project one publication instant per model, without materializing hourly windows."""
    # Bind each eligible run before expanding the security-barrier view. OFFSET 0
    # keeps PostgreSQL from flattening this lateral lookup into a global join;
    # the view still validates every mapping, reference and cross-run owner.
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT DISTINCT ON (p.external_identifier)
            p.external_identifier,p.updated_at
            FROM collection_jobs j
            JOIN collection_runs r ON r.job_id=j.id
            CROSS JOIN LATERAL (
                SELECT p.external_identifier,p.updated_at
                FROM benchmark_endpoint_revisions p
                WHERE p.run_id=r.id
                OFFSET 0
            ) p
            WHERE j.contract_id=%s
                AND j.purpose='metric' AND j.source_id='opencode'
                AND r.status IN ('success','partial')
            ORDER BY p.external_identifier,p.updated_at DESC
            LIMIT 101""",
            [contract.pk],
        )
        rows = cursor.fetchall()
    require(len(rows) <= 100, "OpenCode publication cohort budget")
    return dict(rows)


def selected_identity_rows(contract, source):
    """Latest checked observation per identity, found without any mapping.

    A row's identity is (source, source_identifier, category_key, config_key)
    within the contract. Each successful or partial check references the rows
    current for its publication; the latest publication date, then the latest
    run, decides. A stale check references nothing and so never selects.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT DISTINCT ON (o.source_identifier,o.category_key,o.config_key) o.id
            FROM collection_jobs j
            JOIN collection_runs r ON r.job_id=j.id
            JOIN collection_observations marker ON marker.run_id=r.id
            JOIN collection_observation_inputs i ON i.observation_id=marker.id
                AND i.input_role='endpoint_revision_row'
            JOIN collection_observations o ON o.id=i.input_observation_id
            WHERE j.contract_id=%s AND j.source_id=%s AND j.purpose='metric'
                AND r.status IN ('success','partial')
                AND marker.observation_kind='endpoint_check' AND marker.status='ok'
                AND o.status='ok'
            ORDER BY o.source_identifier,o.category_key,o.config_key,
                marker.source_record_date DESC,r.completed_at DESC,r.id DESC
            LIMIT 100001""",
            [contract.pk, source],
        )
        ids = [row[0] for row in cursor.fetchall()]
    require(len(ids) <= 100000, "revision selection budget exceeded")
    rows = CollectionObservation.objects.filter(pk__in=ids).only(
        "id", "source_identifier", "category_key", "config_key", "mapping_id",
        "row_semantic_digest",
    )
    return {stored_identity(row): row for row in rows}


def reuse_unchanged(prepared, current, identity, *, supersede=False, conflict=False):
    """Split rows into new evidence and references to equal prior observations."""
    new, reused = [], []
    for observation, values in prepared:
        if observation["status"] != "ok":
            new.append((observation, values))
            continue
        key = identity(observation)
        prior = current.get(key)
        if prior and bytes(prior.row_semantic_digest or b"") == bytes.fromhex(
            observation["source_metadata"]["row_semantic_hash"]
        ):
            reused.append((key, prior, observation))
            continue
        if supersede and prior:
            observation["supersedes_observation"] = prior
        if conflict:
            observation["revision_conflict"] = True
        new.append((observation, values))
    return new, reused


def prepare_gdpx_revisions(contract, prepared, payload):
    """Compare a validated GDPx dataset with the latest stored selection (KTD7)."""
    dataset = payload["dataset"]
    day = native_date(dataset["updatedAt"])
    check = {
        "source_identifier": GDPX_DATASET_IDENTIFIER,
        "status": "ok",
        "updated_at": day.isoformat(),
        "body_sha256": payload["dataset_sha256"],
        "row_references": {},
    }
    require(
        re.fullmatch(r"[0-9a-f]{64}", check["body_sha256"]),
        "GDPx dataset digest required",
    )
    identities = [prepared_identity(o) for o, _ in prepared]
    require(len(identities) == len(set(identities)), "duplicate GDPx observation identity")
    markers = CollectionObservation.objects.filter(
        run__job__contract=contract,
        run__job__source_id="gdpx",
        run__job__purpose="metric",
        run__status__in=["success", "partial"],
        observation_kind="endpoint_check",
        status="ok",
    )
    latest = max(markers.values_list("source_record_date", flat=True), default=None)
    if latest is not None and day < latest:
        check["revision_anomaly"] = "older_than_stored"
        return [], [check], set()
    if markers.filter(source_record_date=day).exclude(
        payload_sha256=check["body_sha256"]
    ).exists():
        check["revision_anomaly"] = "same_update_different_body"
    current = selected_identity_rows(contract, "gdpx")
    new, reused = reuse_unchanged(
        prepared, current, prepared_identity,
        supersede=True, conflict="revision_anomaly" in check,
    )
    for key, prior, _ in reused:
        check["row_references"][key] = prior.pk
    # An identity missing from this publication is an absence fact, never a zero.
    check["absent_rows"] = sorted(set(current) - set(identities))
    check["new_publication"] = latest is None or day > latest
    return new, [check], {key for key, _, _ in reused}


def prepare_revisions(contract, prepared, payload, *, source="opencode"):
    """Compare the entire endpoint window; keep decreased historical corrections."""
    if source == "gdpx":
        return prepare_gdpx_revisions(contract, prepared, payload)
    require(source == "opencode", "unsupported revision source")
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
                    SELECT 1 FROM collection_observations marker
                    JOIN collection_runs r ON r.id=marker.run_id
                    JOIN collection_jobs j ON j.id=r.job_id
                    WHERE j.contract_id=%s AND j.source_id='opencode'
                    AND r.status IN ('success','partial')
                    AND marker.observation_kind='endpoint_check'
                    AND marker.source_identifier=%s
                    AND marker.source_record_at=%s AND marker.payload_sha256<>%s
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
    new, reused = reuse_unchanged(
        prepared,
        {key: row["observation"] for key, row in current.items()},
        lambda o: (o["source_identifier"], o["dimensions"]["date"]),
    )
    successful = set()
    for key, prior, observation in reused:
        by_identifier[key[0]]["row_references"][key[1]] = prior.pk
        if observation["mapping"]:
            successful.add(observation["mapping"].pk)
    return new, checks, successful

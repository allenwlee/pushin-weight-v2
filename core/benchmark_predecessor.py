"""Explicit predecessor interpretation over immutable Arena observations."""

from django.db.models import Min

from core.measurement_taxonomy import require
from core.models import MetricValue


def validate_release_history(preset, taxonomy, mappings, config):
    history = preset.get("release_history")
    for line in preset["lines"]:
        require(
            not line.get("predecessor") or history is not None,
            "predecessor needs release-history preset",
        )
    if history is None:
        return
    lookback = history.get("lookback_days", 30)
    require(
        type(lookback) is int and 0 <= lookback <= 365, "invalid pre-launch lookback"
    )
    require(
        config.get("arena", {}).get("config") == "text",
        "release history requires Arena no style control",
    )
    ranks = [
        line
        for line in preset["lines"]
        if line["source"] == "arena" and line["metric_key"] == "rank"
    ]
    require(len(ranks) == 1, "release history requires one rank line")
    for line in preset["lines"]:
        pred = line.get("predecessor")
        if not pred:
            continue
        require(
            line in ranks and line.get("aggregation", "single") == "single",
            "proxy is exact rank only",
        )
        require(
            line["subject_id"] == preset["launch_anchor"]["product_subject_id"],
            "rank target must be launch product",
        )
        previous = taxonomy.snapshot["subjects"].get(pred.get("subject_id"), {})
        successor = taxonomy.snapshot["subjects"][line["subject_id"]]
        require(
            previous.get("kind") == "product", "predecessor must be reviewed product"
        )
        edges = [
            edge
            for edge in taxonomy.snapshot["relationships"]
            if edge["parent"] == previous["key"]
            and edge["child"] == successor["key"]
            and edge["type"] == "new_version"
        ]
        require(
            len(edges) == 1 and pred.get("rationale"),
            "reviewed predecessor relationship and rationale required",
        )
        identifiers = pred.get("mapping_identifiers", [])
        selected = [
            m
            for m in mappings
            if m["source"] == "arena" and m["external_identifier"] in identifiers
        ]
        require(
            len(identifiers) == len(selected) == 1
            and selected[0]["subject_id"] == pred["subject_id"],
            "predecessor needs one exact Arena mapping",
        )
        require(
            selected[0]["identifier_scope"] == "",
            "predecessor Arena variant/config mismatch",
        )
        own = [
            m
            for m in mappings
            if m["source"] == "arena"
            and m["external_identifier"] in line["mapping_identifiers"]
        ]
        require(
            len(own) == 1 and own[0]["identifier_scope"] == "",
            "successor Arena variant/config mismatch",
        )


def predecessor_points(contract, line, days):
    from core.benchmark_metric_series import metric_points

    successor, definition, mapping_ids = metric_points(contract, line, days)
    first = MetricValue.objects.filter(
        source_metric=definition,
        observation__mapping_id__in=mapping_ids,
        observation__run__contract=contract,
        observation__run__status__in=["success", "partial"],
        observation__status="ok",
    ).aggregate(first=Min("as_of_date"))["first"]
    switch = first.isoformat() if first else None
    pred = line.get("predecessor")
    previous, previous_ids, relationship = None, [], None
    if pred:
        previous, _, previous_ids = metric_points(contract, {**line, **pred}, days)
        parent = contract.catalog_snapshot["subjects"][pred["subject_id"]]["key"]
        child = contract.catalog_snapshot["subjects"][line["subject_id"]]["key"]
        relationship = next(
            edge
            for edge in contract.catalog_snapshot["relationships"]
            if edge["parent"] == parent
            and edge["child"] == child
            and edge["type"] == "new_version"
        )
    points = []
    for index, day in enumerate(days):
        proxy = switch is None or day < switch
        actual = pred["subject_id"] if proxy and pred else line["subject_id"]
        point = dict(
            previous[index] if proxy and previous is not None else successor[index]
        )
        if proxy and previous is None:
            point.update(
                raw_value=None,
                coverage="missing_predecessor",
                evidence=[],
                observed=False,
            )
        point.update(
            target_product_subject_id=line["subject_id"],
            measured_subject_id=actual,
            measured_subject=contract.catalog_snapshot["subjects"][actual],
            measured_mapping_ids=previous_ids if proxy else mapping_ids,
            proxy=bool(proxy and pred),
            proxy_label=f"Previous release proxy — {contract.catalog_snapshot['subjects'][actual]['label']}"
            if proxy and pred
            else None,
            model_changed=day == switch,
            segment="predecessor" if proxy else "successor",
        )
        points.append(point)
    return (
        points,
        definition,
        mapping_ids + previous_ids,
        {
            "switch_date": switch,
            "switch_rule": "first_valid_arena_publication",
            "relationship": relationship,
            "taxonomy_version_id": str(contract.taxonomy_version_id),
            "rationale": pred.get("rationale") if pred else "No reviewed predecessor",
            "segments": [
                {
                    "kind": "predecessor",
                    "start_date": days[0],
                    "end_exclusive": switch,
                    "subject_id": pred["subject_id"] if pred else None,
                    "mapping_ids": previous_ids,
                },
                {
                    "kind": "successor",
                    "start_date": switch,
                    "end_date": days[-1],
                    "subject_id": line["subject_id"],
                    "mapping_ids": mapping_ids,
                },
            ],
        },
    )

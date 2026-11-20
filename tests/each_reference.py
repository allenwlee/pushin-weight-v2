"""Frozen per-post chart reference from production source 9ed25df7.

The intentional Role correction matches account UUIDs. Sentiment always uses
its existing scalar reader rather than the optimized SQL aggregate.
"""

from __future__ import annotations

from monitor.views import (
    _DASHBOARD_LANG_FILTER_KEYS_BY_PERSISTED_VALUE,
    _DEFAULT_BRAND_ACCENT,
    _EACH_FIXED_COLORS,
    _FILTER_NO_AUDIENCE_TOPIC,
    _FILTER_NO_PRODUCT_SIGNAL,
    _FILTER_UNCLASSIFIED,
    COMPATIBLE_TAXONOMY_VERSIONS,
    CONTRACT_VERSION,
    UTC,
    Any,
    AudienceTopicScheme,
    BrandAccount,
    PostBrand,
    PostBrandAudienceTopic,
    PostBrandClassificationState,
    PostBrandGeopoliticalMode,
    PostBrandProductLabel,
    PostBrandSignal,
    PostUntrackedBrandPromotion,
    Q,
    _build_brands_context,
    _dashboard_canonical_key,
    _dashboard_now,
    _each_ordered_entries,
    _each_tab_entries,
    _one_day_chart_end,
    _post_language_expression,
    _resolve_chart_timezone,
    canonicalize_taxonomy_key,
    datetime,
    normalize_lang_detected,
    read_brand_scalars_many,
    timedelta,
)


def reference_each_chart_payload(
    brand: str,
    tab: str,
    window_days: int,
    locale: str,
    *,
    now: datetime | None = None,
    bucket_timezone: str = "UTC",
    _rank: bool = True,
) -> dict[str, Any]:
    """Count one brand's current classification assignments without a feed row cap."""
    from itertools import islice

    at = now or _dashboard_now()
    from monitor.harvest_coverage import (
        closed_five_minute_boundary,
        latest_scheduled_coverage,
    )

    coverage = latest_scheduled_coverage(at) if window_days == 1 else None
    requested_at = at
    timezone_name, tzinfo = _resolve_chart_timezone(
        bucket_timezone if window_days > 1 else "UTC"
    )
    local_today = at.astimezone(tzinfo).date()
    if window_days == 1:
        start = closed_five_minute_boundary(at) - timedelta(days=1)
        at = _one_day_chart_end(at, coverage)
        buckets = max(0, int((at - start).total_seconds() // 300))
        labels = [
            (start + timedelta(minutes=5 * i)).isoformat() for i in range(buckets)
        ]
    else:
        first = local_today - timedelta(days=window_days - 1)
        start = datetime(first.year, first.month, first.day, tzinfo=tzinfo).astimezone(
            UTC
        )
        labels = [(first + timedelta(days=i)).isoformat() for i in range(window_days)]
    entries = _each_tab_entries(locale)[tab]
    keys = [entry["key"] for entry in entries]
    # Use the same ordered accent palette that colors the homepage model lines.
    reference_priority = (
        'llama', 'deepseek', 'qwen', 'minimax', 'glm', 'mimo', 'moonshot_kimi',
        'inclusionai', 'mistral', 'stepfun', 'ernie', 'hunyuan', 'nemo_megatron',
        'doubao', 'yi', 'sensechat', 'exaone', 'kuaishou', 'sakana_ai', 'upstage',
        'chatglm', 'gemma', 'kwaiyii', 'seed', 'sensenova', 'wenxin', 'gemini',
        'gpt', 'claude', 'grok',
    )
    reference_rank = {key: index for index, key in enumerate(reference_priority)}
    reference_brands = sorted(_build_brands_context(), key=lambda row: (
        reference_rank.get(row['nickname'], len(reference_rank)), row['nickname']))
    palette = [item['accent_color'] for item in reference_brands] or [_DEFAULT_BRAND_ACCENT]
    series = {key: [0] * len(labels) for key in keys}
    totals = [0] * len(labels)
    day_index = (
        {day: index for index, day in enumerate(labels)} if window_days > 1 else {}
    )

    def bucket_index(created: datetime) -> int | None:
        if window_days == 1:
            index = max(0, int((created - start).total_seconds() // 300))
            return index if index < len(labels) else None
        return day_index.get(created.astimezone(tzinfo).date().isoformat())

    sentiment_counts = None
    if sentiment_counts is not None:
        for bucket, sentiment, count in sentiment_counts:
            index = day_index.get(bucket.isoformat()) if window_days > 1 else bucket
            if index is not None and 0 <= index < len(labels):
                totals[index] += count
                key = sentiment or _FILTER_UNCLASSIFIED
                if key in series:
                    series[key][index] += count

    rows = (
        PostBrand.objects.filter(
            brand_id=brand,
            post__created_at__gte=start,
            post__created_at__lt=at,
        )
        .annotate(_effective_post_language=_post_language_expression("post__"))
        .order_by()
        .values_list(
            "post_id",
            "post__created_at",
            "_effective_post_language",
            "post__author_id",
        )
        .iterator(chunk_size=5000)
        if sentiment_counts is None
        else iter(())
    )
    audience_revision = None
    if tab == "audience_topics":
        audience_revision = (
            AudienceTopicScheme.objects.filter(key="ai_audience_topics/v1")
            .values_list("revision", flat=True)
            .first()
        )

    while batch := list(islice(rows, 5000)):
        post_ids = [row[0] for row in batch]
        assigned: dict[str, set[str]] = {post_id: set() for post_id in post_ids}
        state: dict[str, tuple[str, str, str]] = {}
        if tab in {"post_types", "product_labels", "audience_topics"}:
            state = {
                row["post_id"]: (
                    row["contract_version"],
                    row["taxonomy_version"],
                    row["outcome"],
                )
                for row in PostBrandClassificationState.objects.filter(
                    brand_id=brand,
                    post_id__in=post_ids,
                ).values("post_id", "contract_version", "taxonomy_version", "outcome")
            }
        if tab == "sentiment":
            reads = read_brand_scalars_many([(post_id, brand) for post_id in post_ids])
            for post_id in post_ids:
                assigned[post_id].add(
                    reads[(post_id, brand)].sentiment or _FILTER_UNCLASSIFIED
                )
        elif tab == "post_types":
            edges = PostBrandSignal.objects.filter(
                brand_id=brand, post_id__in=post_ids
            ).values_list("post_id", "post_type_id")
            for post_id, raw_key in edges:
                current = state.get(post_id)
                if (
                    current
                    and current[0] == CONTRACT_VERSION
                    and current[1] in COMPATIBLE_TAXONOMY_VERSIONS
                    and current[2] == "classified"
                ):
                    # The v2 combined concept cannot become an exact v3 event
                    # or opportunity assignment on this chart.
                    if raw_key == "events_opportunities":
                        continue
                    key = _dashboard_canonical_key("post_type", raw_key)
                    if key in series:
                        assigned[post_id].add(key)
            for post_id in post_ids:
                if not assigned[post_id]:
                    assigned[post_id].add(_FILTER_UNCLASSIFIED)
        elif tab == "product_labels":
            edges = PostBrandProductLabel.objects.filter(
                brand_id=brand, post_id__in=post_ids
            ).values_list("post_id", "product_label_id")
            for post_id, raw_key in edges:
                current = state.get(post_id)
                if (
                    current
                    and current[0] == CONTRACT_VERSION
                    and current[1] in COMPATIBLE_TAXONOMY_VERSIONS
                    and current[2] == "classified"
                ):
                    key = canonicalize_taxonomy_key("product_label", raw_key)
                    if key in series:
                        assigned[post_id].add(key)
            for post_id in post_ids:
                if not assigned[post_id]:
                    current = state.get(post_id)
                    classified = (
                        current
                        and current[0] == CONTRACT_VERSION
                        and current[1] in COMPATIBLE_TAXONOMY_VERSIONS
                        and current[2] == "classified"
                    )
                    assigned[post_id].add(
                        _FILTER_NO_PRODUCT_SIGNAL
                        if classified
                        else _FILTER_UNCLASSIFIED
                    )
        elif tab == "audience_topics" and audience_revision is not None:
            edges = PostBrandAudienceTopic.objects.filter(
                brand_id=brand,
                post_id__in=post_ids,
                scheme_id="ai_audience_topics/v1",
                scheme_revision=audience_revision,
            ).values_list("post_id", "concept__key")
            for post_id, raw_key in edges:
                key = _dashboard_canonical_key("audience_topic", raw_key)
                if key in series:
                    assigned[post_id].add(key)
            for post_id in post_ids:
                if not assigned[post_id]:
                    current = state.get(post_id)
                    available = current and (
                        "v4" in current[1].lower() or "u18a" in current[1].lower()
                    )
                    assigned[post_id].add(
                        _FILTER_NO_AUDIENCE_TOPIC if available else _FILTER_UNCLASSIFIED
                    )
        elif tab == "audience_topics":
            for post_id in post_ids:
                assigned[post_id].add(_FILTER_UNCLASSIFIED)
        elif tab == "geopolitical_modes":
            edges = (
                PostBrandGeopoliticalMode.objects.filter(
                    brand_id=brand,
                    post_id__in=post_ids,
                )
                .filter(
                    Q(taxonomy_version__icontains="v4")
                    | Q(taxonomy_version__icontains="u18a")
                )
                .values_list("post_id", "geopolitical_mode_id")
            )
            for post_id, raw_key in edges:
                key = _dashboard_canonical_key("geopolitical_mode", raw_key)
                if key in series:
                    assigned[post_id].add(key)
        elif tab == "untracked_brand_promotions":
            for post_id, raw_keys in PostUntrackedBrandPromotion.objects.filter(
                post_id__in=post_ids
            ).values_list("post_id", "promotion_keys"):
                for raw_key in raw_keys if isinstance(raw_keys, list) else []:
                    key = _dashboard_canonical_key(
                        "untracked_brand_promotion", str(raw_key)
                    )
                    if key in series:
                        assigned[post_id].add(key)
        elif tab == "role":
            authors = {author_id for _, _, _, author_id in batch if author_id}
            role_by_author = dict(
                BrandAccount.objects.filter(account__data_source_id="x")
                .filter(brand_id=brand, account_id__in=authors)
                .values_list("account_id", "role_id")
            )
            for post_id, _, _, author_id in batch:
                role = role_by_author.get(author_id)
                assigned[post_id].add(
                    role if role in series and role != "other" else "other"
                )
        elif tab == "lang":
            for post_id, _, detected, _ in batch:
                normalized = normalize_lang_detected(detected) if detected else None
                key = _DASHBOARD_LANG_FILTER_KEYS_BY_PERSISTED_VALUE.get(
                    normalized, normalized
                )
                if key in series:
                    assigned[post_id].add(key)
                elif not key:
                    assigned[post_id].add("undetected")
                else:
                    assigned[post_id].add("other")

        for post_id, created, _, _ in batch:
            index = bucket_index(created)
            if index is None:
                continue
            totals[index] += 1
            for key in assigned[post_id]:
                if key in series:
                    series[key][index] += 1

    original_colors = {
        entry["key"]: palette[i % len(palette)] for i, entry in enumerate(entries)
    }
    if _rank:
        entries = _each_ordered_entries(tab, entries, at, cache_result=now is None)
    return {
        "brand": brand,
        "tab": tab,
        "window_days": window_days,
        "bucket_timezone": timezone_name,
        "granularity": "minute" if window_days == 1 else "day",
        "days": labels,
        "series": series,
        "totals": totals,
        "entries": [
            {
                "key": entry["key"],
                "label": entry["label"],
                "color": _EACH_FIXED_COLORS.get(
                    entry["key"], original_colors[entry["key"]]
                ),
            }
            for entry in entries
        ],
        "counting_unit": "posts"
        if tab in {"sentiment", "lang", "role"}
        else "label_assignments",
        "computed_at": requested_at.isoformat(),
        "harvest_coverage": coverage,
    }

"""Reusable exact-window counts of current stored discussion and classifications.

No Post membership is persisted per window or dossier. A fingerprint of the
actual rows invalidates changed inputs. Old snapshots and their figures survive.
This is a current-projection historical analysis, never an as-known-then replay.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict, deque
from datetime import UTC

from django.db import connection, transaction
from django.utils import timezone

from core import models
from core.classification_analysis import (
    LEGACY_DASHBOARD_POST_TYPE_KEYS,
    AnalysisRequest,
    _validate_request,
)
from core.classification_contract import (
    COMPATIBLE_TAXONOMY_VERSIONS,
    CONTRACT_VERSION,
    taxonomy_crosswalk_rows,
)
from core.event_dossiers import _digest
from core.product_release_replay import ReplayWindow

METHOD = "discussion-window-v1"


def _inputs(brand_id, start, end):
    scope = models.Post.objects.filter(
        brands__brand_id=brand_id, created_at__gte=start, created_at__lt=end
    )
    posts = list(
        scope.order_by("created_at", "pk").values(
            "tweet_id",
            "author_id",
            "native_author_id",
            "author_handle",
            "created_at",
            "fetched_at",
            "lang",
            "lang_detected",
        )
    )
    ids = scope.values("pk")
    states = {
        row["post_id"]: row
        for row in models.PostBrandClassificationState.objects.filter(
            post_id__in=ids, brand_id=brand_id
        ).values(
            "post_id",
            "contract_version",
            "taxonomy_version",
            "prompt_version",
            "model",
            "outcome",
            "sentiment_id",
            "classified_at",
            "input_context_fingerprint",
        )
    }
    projections = {}
    for name, model, fields in (
        ("signals", models.PostBrandSignal, ("post_type_id", "sentiment_id")),
        (
            "audience",
            models.PostBrandAudienceTopic,
            ("concept__key", "scheme_id", "scheme_revision", "prompt_version", "model"),
        ),
        (
            "geopolitics",
            models.PostBrandGeopoliticalMode,
            ("geopolitical_mode_id", "taxonomy_version", "prompt_version", "model"),
        ),
    ):
        grouped = defaultdict(list)
        for row in (
            model.objects.filter(post_id__in=ids, brand_id=brand_id)
            .order_by("post_id", *fields)
            .values("post_id", *fields)
        ):
            grouped[row["post_id"]].append(row)
        projections[name] = grouped
    return posts, states, projections


def _calculate(posts, states, projections, history_policy):
    members, denominators = defaultdict(set), defaultdict(set)
    crosswalk = dict(taxonomy_crosswalk_rows("post_type"))

    def put(population, dimension, definition, category, post_id):
        members[(population, dimension, definition, category)].add(post_id)

    def denominator(population, dimension, definition, post_id):
        denominators[(population, dimension, definition)].add(post_id)

    for post in posts:
        post_id = post["tweet_id"]
        put("all", "volume", "stored-posts-v1", "posts", post_id)
        denominator("all", "volume", "stored-posts-v1", post_id)
        language = (post["lang_detected"] or post["lang"] or "und").strip()
        # Keep provider language codes separate from normalized classification.
        put(
            "all",
            "language",
            "post-language-observed-v1",
            language[:160] or "und",
            post_id,
        )
        denominator("all", "language", "post-language-observed-v1", post_id)
        state = states.get(post_id)
        valid = (
            state
            and state["contract_version"] == CONTRACT_VERSION
            and state["taxonomy_version"] in COMPATIBLE_TAXONOMY_VERSIONS
            and state["outcome"] in {"classified", "context_missing"}
        )
        if valid:
            pop, definition = "exact", state["taxonomy_version"]
            outcome = state["outcome"]
        elif state:
            pop, definition, outcome = (
                "excluded",
                "unrecognized-state-v1",
                "unrecognized",
            )
        else:
            pop, definition, outcome = "legacy", "unversioned-v1", "unversioned"
        put(pop, "classification", definition, outcome, post_id)
        denominator(pop, "classification", definition, post_id)
        if not valid or outcome != "classified":
            if state or history_policy != "historical_inclusive":
                continue
            signals = [
                s
                for s in projections["signals"][post_id]
                if s["post_type_id"] in LEGACY_DASHBOARD_POST_TYPE_KEYS
            ]
            if not signals:
                continue
            for signal in signals:
                put(
                    "legacy",
                    "post_type",
                    definition,
                    crosswalk[signal["post_type_id"]],
                    post_id,
                )
                put("legacy", "sentiment", definition, signal["sentiment_id"], post_id)
            denominator("legacy", "post_type", definition, post_id)
            denominator("legacy", "sentiment", definition, post_id)
            continue
        for dim in ("post_type", "sentiment"):
            denominator(pop, dim, definition, post_id)
        put(
            pop,
            "sentiment",
            definition,
            state["sentiment_id"] or "unavailable",
            post_id,
        )
        for signal in projections["signals"][post_id]:
            category = crosswalk.get(signal["post_type_id"])
            if category:
                put(pop, "post_type", definition, category, post_id)
        # These independently versioned assignments use their own covered
        # population. Missing assignments do not mean a zero/neutral label.
        for row in projections["audience"][post_id]:
            definition = f"{row['scheme_id']}:{row['scheme_revision']}"
            put(pop, "audience", definition, row["concept__key"], post_id)
            denominator(pop, "audience", definition, post_id)
        for row in projections["geopolitics"][post_id]:
            definition = row["taxonomy_version"]
            put(pop, "geopolitics", definition, row["geopolitical_mode_id"], post_id)
            denominator(pop, "geopolitics", definition, post_id)
    return [
        {
            "population": p,
            "dimension": d,
            "definition": v,
            "category": c,
            "count": len(ids),
            "denominator": len(denominators[(p, d, v)]),
        }
        for (p, d, v, c), ids in sorted(members.items())
    ]


def _capture_windows(brand_id, windows, *, history_policy="historical_inclusive"):
    """Read one consistent population and save/reuse several exact windows."""
    if history_policy not in {"current_definition", "historical_inclusive"}:
        raise ValueError(
            "Unsupported history_policy; current projections cannot prove as-known history"
        )
    windows = [ReplayWindow(start, end) for start, end in windows]
    if not windows or len(windows) > 3000:
        raise ValueError("Supply 1..3000 windows")
    if connection.in_atomic_block:
        raise ValueError("Discussion capture requires its own consistent transaction")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        request = _validate_request(
            AnalysisRequest(
                history_policy,
                min(w.start for w in windows),
                max(w.end for w in windows),
                (brand_id,),
            )
        )
        brand_id = request.brands[0]
        posts, states, projections = _inputs(brand_id, request.start, request.end)
        observed_at = timezone.now()
        subject, _ = models.MeasurementSubject.objects.get_or_create(
            brand_id=brand_id, defaults={"subject_kind": "brand"}
        )
        timestamps = [p["created_at"] for p in posts]
        result = []
        for window in windows:
            selected = posts[
                bisect_left(timestamps, window.start) : bisect_left(
                    timestamps, window.end
                )
            ]
            ids = [p["tweet_id"] for p in selected]
            packet = [
                selected,
                [states.get(pk) for pk in ids],
                {name: [rows[pk] for pk in ids] for name, rows in projections.items()},
            ]
            input_hash = _digest(packet)
            accounts = {
                str(p["author_id"] or p["native_author_id"])
                for p in selected
                if p["author_id"] or p["native_author_id"]
            }
            missing_authors = sum(
                not (p["author_id"] or p["native_author_id"]) for p in selected
            )
            counts = _calculate(selected, states, projections, history_policy)
            snapshot, created = models.DiscussionWindowSnapshot.objects.get_or_create(
                subject=subject,
                window_start=window.start,
                window_end=window.end,
                method_version=METHOD,
                history_policy=history_policy,
                input_hash=input_hash,
                defaults={
                    "observed_at": observed_at,
                    "knowledge_cutoff_at": observed_at,
                    "post_count": len(selected),
                    "account_count": len(accounts),
                    "count_rows": len(counts),
                    "coverage": "stored_only" if selected else "no_stored_posts",
                    "coverage_note": f"Current stored classifications; historical completeness unverified; {missing_authors} posts lack a stable author identity. Audience/geopolitical denominators count assigned posts only.",
                },
            )
            if created:
                models.DiscussionWindowCount.objects.bulk_create(
                    [
                        models.DiscussionWindowCount(snapshot=snapshot, **row)
                        for row in counts
                    ]
                )
            result.append((snapshot, created))
        return result


def capture_windows(brand_id, windows, *, history_policy="historical_inclusive"):
    """Serialize same-brand calculations before taking a repeatable snapshot."""
    if connection.in_atomic_block:
        raise ValueError("Discussion capture requires its own consistent transaction")
    key = int(_digest(["discussion-capture", brand_id])[:15], 16)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
        if not cursor.fetchone()[0]:
            raise ValueError("Discussion capture for this brand is busy; retry later")
    try:
        return _capture_windows(brand_id, windows, history_policy=history_policy)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [key])


def capture_window(brand_id, start, end, *, history_policy="historical_inclusive"):
    return capture_windows(brand_id, [(start, end)], history_policy=history_policy)[0]


def read_window(snapshot_id):
    snapshot = models.DiscussionWindowSnapshot.objects.get(pk=snapshot_id)
    return {
        "id": str(snapshot.pk),
        "subject_id": str(snapshot.subject_id),
        "window_start": snapshot.window_start.astimezone(UTC).isoformat(),
        "window_end": snapshot.window_end.astimezone(UTC).isoformat(),
        "observed_at": snapshot.observed_at.isoformat(),
        "window_elapsed_at_capture": snapshot.window_end
        <= snapshot.knowledge_cutoff_at,
        "post_count": snapshot.post_count,
        "account_count": snapshot.account_count,
        "coverage": snapshot.coverage,
        "coverage_note": snapshot.coverage_note,
        "method_version": snapshot.method_version,
        "history_policy": snapshot.history_policy,
        "input_hash": snapshot.input_hash,
        "counts": list(
            snapshot.counts.order_by(
                "population", "dimension", "definition", "category"
            ).values(
                "population",
                "dimension",
                "definition",
                "category",
                "count",
                "denominator",
            )
        ),
    }


def discussion_packet(snapshot_id, *, source_limit=16):
    """Select contrasting examples without persisting the counted population.

    Quartiles and language/sentiment strata keep the middle of a window visible.
    These are inspectable examples, not an exhaustive topic summary.
    """
    if not 1 <= source_limit <= 40:
        raise ValueError("source_limit must be 1..40")
    if connection.in_atomic_block:
        raise ValueError("Discussion packet requires its own consistent transaction")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        snapshot = models.DiscussionWindowSnapshot.objects.select_related(
            "subject"
        ).get(pk=snapshot_id)
        if snapshot.subject.subject_kind != "brand":
            raise ValueError("Discussion packet currently requires a brand subject")
        posts, states, projections = _inputs(
            snapshot.subject.brand_id, snapshot.window_start, snapshot.window_end
        )
        ids = [p["tweet_id"] for p in posts]
        fingerprint = _digest(
            [
                posts,
                [states.get(pk) for pk in ids],
                {name: [rows[pk] for pk in ids] for name, rows in projections.items()},
            ]
        )
        if fingerprint != snapshot.input_hash:
            raise ValueError(
                "Stored discussion inputs changed; capture a new window before selecting sources"
            )
        strata = defaultdict(list)
        seconds = (snapshot.window_end - snapshot.window_start).total_seconds()
        for post in posts:
            quartile = min(
                3,
                int(
                    4
                    * (post["created_at"] - snapshot.window_start).total_seconds()
                    / seconds
                ),
            )
            state = states.get(post["tweet_id"]) or {}
            language = post["lang_detected"] or post["lang"] or "und"
            strata[
                (quartile, language, state.get("sentiment_id") or "unavailable")
            ].append(post)
        # Balance time first. A multilingual first quartile must not consume the
        # entire quota before a middle-window surge gets a representative source.
        queues = {}
        for quartile in range(4):
            groups = [
                deque(strata[key]) for key in sorted(strata) if key[0] == quartile
            ]
            queue = deque()
            while any(groups):
                for group in groups:
                    if group:
                        queue.append(group.popleft())
            queues[quartile] = queue
        selected, accounts = [], defaultdict(int)
        while any(queues.values()) and len(selected) < source_limit:
            for queue in queues.values():
                while queue:
                    post = queue.popleft()
                    account = str(
                        post["author_id"]
                        or post["native_author_id"]
                        or post["tweet_id"]
                    )
                    if accounts[account] >= 2:
                        continue
                    selected.append(post["tweet_id"])
                    accounts[account] += 1
                    break
                if len(selected) == source_limit:
                    break
        sources = {p.pk: p for p in models.Post.objects.filter(pk__in=selected)}
        examples = [
            {
                "post_id": key,
                "account_id": str(sources[key].author_id)
                if sources[key].author_id
                else None,
                "native_author_id": sources[key].native_author_id,
                "name": sources[key].author_name
                or sources[key].author_handle
                or "Unknown account",
                "handle": sources[key].author_handle,
                "text": sources[key].text or "",
                "created_at": sources[key].created_at.isoformat(),
                "url": sources[key].tweet_url or f"https://x.com/i/status/{key}",
            }
            for key in selected
        ]
        result = read_window(snapshot.pk)
        result.update(
            sources=examples,
            supplied_post_count=len(examples),
            supplied_account_count=len(
                {
                    s["account_id"] or s["native_author_id"]
                    for s in examples
                    if s["account_id"] or s["native_author_id"]
                }
            ),
            source_selection="quartile-language-sentiment-examples-v2",
            source_limit=source_limit,
            attribution="brand discussion; examples are not automatically attributable to one release",
        )
        return result

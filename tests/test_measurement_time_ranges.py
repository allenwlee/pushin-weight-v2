"""Measurement intervals are enforced in PostgreSQL, including direct SQL."""

from datetime import UTC, datetime, timedelta

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction

from core.models import MetricValue
from tests.test_benchmark_download_persistence import configured, payload

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]

START = datetime(2026, 10, 5, tzinfo=UTC)
END = START + timedelta(days=1)


def test_metric_window_tables_share_the_database_constructor():
    from django.apps import apps
    from django.db.models import GeneratedField

    for model in apps.get_app_config("core").get_models():
        fields = {f.name: f for f in model._meta.local_fields}
        if {"window_start_at", "window_end_at"} <= fields.keys():
            assert isinstance(fields.get("window_range"), GeneratedField), (
                model.__name__
            )
            expression = fields["window_range"].expression
            assert (
                expression.extra.get("function", expression.function)
                == "measurement_window_v1"
            )


def values():
    from core.benchmark_metric_store import persist_source

    persist_source(configured(), "hf", "7" * 64, payload())
    return list(MetricValue.objects.order_by("pk"))


def test_generated_range_is_database_owned_and_complete_window_is_half_open():
    value = values()[0]
    value.window_start_at, value.window_end_at = START, END
    value.save(update_fields=["window_start_at", "window_end_at"])
    value.refresh_from_db()
    assert MetricValue._meta.get_field("window_range").generated
    assert value.window_range.lower == START
    assert value.window_range.upper == END
    assert value.window_range.lower_inc and not value.window_range.upper_inc
    assert MetricValue.objects.filter(
        pk=value.pk, window_range__contains=START
    ).exists()
    assert MetricValue.objects.filter(
        pk=value.pk, window_range__contains=END - timedelta(microseconds=1)
    ).exists()
    assert not MetricValue.objects.filter(
        pk=value.pk, window_range__contains=END
    ).exists()
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as c:
        c.execute(
            "UPDATE metric_values SET window_range = tstzrange(%s, %s, '[]') WHERE id = %s",
            [START, END, value.pk],
        )


@pytest.mark.parametrize("start,end", [(None, None), (START, None), (None, END)])
def test_raw_sql_preserves_partial_bounds_and_unknown_ranges_never_overlap(start, end):
    value = values()[0]
    with connection.cursor() as c:
        c.execute(
            "UPDATE metric_values SET window_start_at=%s, window_end_at=%s WHERE id=%s",
            [start, end, value.pk],
        )
        c.execute(
            "SELECT window_range IS NULL, window_range && tstzrange(%s,%s,'[)') FROM metric_values WHERE id=%s",
            [START, END, value.pk],
        )
        assert c.fetchone() == (True, None)
    value.refresh_from_db()
    assert (value.window_start_at, value.window_end_at) == (start, end)
    assert value.window_range is None


@pytest.mark.parametrize(
    "start,end",
    [
        (START, START),
        (END, START),
        ("-infinity", END),
        (START, "infinity"),
        ("infinity", None),
        (None, "-infinity"),
    ],
)
def test_raw_sql_rejects_empty_reversed_and_nonfinite_windows(start, end):
    value = values()[0]
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as c:
        c.execute(
            "UPDATE metric_values SET window_start_at=%s::timestamptz, window_end_at=%s::timestamptz WHERE id=%s",
            [start, end, value.pk],
        )
    value.refresh_from_db()
    assert value.window_range is None


def test_bulk_update_recomputes_ranges_and_equivalent_offsets_preserve_instants():
    rows = values()
    for value in rows:
        value.window_start_at, value.window_end_at = START, END
    MetricValue.objects.bulk_update(rows, ["window_start_at", "window_end_at"])
    assert MetricValue.objects.filter(window_range__contains=START).count() == 2
    with connection.cursor() as c:
        c.execute(
            "UPDATE metric_values SET window_start_at='2026-10-05 09:00:00+09', window_end_at='2026-10-06 09:00:00+09' WHERE id=%s",
            [rows[0].pk],
        )
    rows[0].refresh_from_db()
    assert rows[0].window_range.lower == START
    assert rows[0].window_range.upper == END
    rows[0].window_end_at = None
    rows[0].save(update_fields=["window_end_at"])
    rows[0].refresh_from_db()
    assert rows[0].window_range is None and rows[0].window_start_at == START


def test_future_tables_can_reuse_the_database_rule_without_application_validation():
    with connection.cursor() as c:
        c.execute(
            "CREATE TEMP TABLE future_metric_window (start_at timestamptz, end_at timestamptz, period tstzrange GENERATED ALWAYS AS (measurement_window_v1(start_at, end_at)) STORED) ON COMMIT DROP"
        )
        c.execute(
            "INSERT INTO future_metric_window(start_at,end_at) VALUES(%s,%s),(%s,NULL)",
            [START, END, START],
        )
        c.execute(
            "SELECT period IS NULL, lower_inc(period), upper_inc(period) FROM future_metric_window ORDER BY end_at NULLS LAST"
        )
        assert c.fetchall() == [(False, True, False), (True, None, None)]
        with pytest.raises(IntegrityError), transaction.atomic():
            c.execute(
                "INSERT INTO future_metric_window(start_at,end_at) VALUES(NULL,'infinity')"
            )


def test_dst_windows_keep_real_duration_and_database_boundary_metadata():
    from core.benchmark_metric_store import calendar_window

    with connection.cursor() as c:
        for date, hours in [("2026-03-08", 23), ("2026-11-01", 25)]:
            start, end = calendar_window(date, "America/New_York")
            c.execute(
                "SELECT upper(w)-lower(w), lower_inc(w), upper_inc(w) FROM (SELECT measurement_window_v1(%s,%s) w) q",
                [start, end],
            )
            assert c.fetchone() == (timedelta(hours=hours), True, False)

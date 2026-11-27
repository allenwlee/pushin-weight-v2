"""GDPx persistence: one observation per published cell, revision reuse, KTD9 success."""

from copy import deepcopy
from datetime import date
from functools import lru_cache
from types import SimpleNamespace

import pytest

from core.benchmark_gdpx import canonical_digest, expected_observation_count

RESULTS, OVERALL = 367, 26
EXPECTED = RESULTS + OVERALL


@lru_cache(maxsize=1)
def _recorded():
    from tests.test_benchmark_gdpx import read

    return read()


def payload(change=None, *, updated=None):
    """The recorded reader payload, optionally edited and re-identified."""
    data = deepcopy(_recorded())
    dataset = data["dataset"]
    if change is not None:
        change(dataset)
    if updated is not None:
        dataset["updatedAt"] = updated
    data["updated_at"] = dataset["updatedAt"]
    data["dataset_sha256"] = canonical_digest(dataset)
    data["expected_observation_count"] = expected_observation_count(dataset)
    return data


def result(dataset, model_id, partner_id):
    return next(
        row
        for row in dataset["results"]
        if row["modelId"] == model_id and row["partnerId"] == partner_id
    )


def contract():
    from core.benchmark_metric_identity import configure_collection
    from tests.test_benchmark_gdpx_definitions import gdpx_spec

    return configure_collection(gdpx_spec())


def persist(target, key, data):
    from core.benchmark_metric_store import persist_source

    return persist_source(target, "gdpx", key * 64, data)


def rows(run):
    from core.models import CollectionObservation

    return CollectionObservation.objects.filter(run=run, observation_kind__isnull=True)


def check(run):
    from core.models import CollectionObservation

    return CollectionObservation.objects.get(run=run, observation_kind="endpoint_check")


def links(run):
    from core.models import CollectionObservationInput

    return CollectionObservationInput.objects.filter(
        observation=check(run), input_role="endpoint_revision_row"
    )


def archived_check(run):
    from core.collection_capture import read_document

    (only,) = read_document(run.source_metadata_archive)["endpoint_checks"]
    return only


# --- pure adapter scenarios ---------------------------------------------------


def native(data):
    from core.benchmark_metric_store import native_rows

    return list(native_rows("gdpx", data))


def test_adapter_maps_every_result_and_overall_entry_with_ktd8_coordinates():
    data = payload()
    out = native(data)
    assert len(out) == EXPECTED == data["expected_observation_count"]
    partners = data["partners"]
    cell = next(
        r
        for r in out
        if r["source_identifier"] == "claude-fable-5-2"
        and r["dimensions"]["category"] == "fleet"
    )
    assert cell["dimensions"] == {
        "category": "fleet",
        "coordinate": partners["fleet"]["domain"],
        "config": "Claude Code|max",
        "date": "2026-11-25",
    }
    assert cell["published_date"] == "2026-11-25"
    assert cell["publication_precision"] == "date"
    assert cell["metrics"]["score"]["value"] == 9.29
    assert cell["metrics"]["tasks"]["value"] == 18
    assert cell["metrics"]["cost_per_task"]["value"] == 20.2
    overall = [r for r in out if r["dimensions"]["category"] == "overall"]
    assert len(overall) == OVERALL
    assert all("coordinate" not in r["dimensions"] for r in overall)
    assert all(
        set(r["metrics"]) <= {"cost_per_task", "tokens_per_task"} for r in overall
    )


def test_reasoning_spelling_shares_a_config_and_harness_change_splits_it():
    def respell(dataset):
        for model in dataset["models"]:
            if model["id"] == "qwen-4-max":
                assert model["reasoning"] == "XHigh"
                model["reasoning"] = "xHigh"

    def config(data, model_id):
        return {
            r["dimensions"]["config"]
            for r in native(data)
            if r["source_identifier"] == model_id
        }

    assert config(payload(), "qwen-4-max") == {"Claude Code|xhigh"}
    assert config(payload(respell), "qwen-4-max") == {"Claude Code|xhigh"}
    assert config(payload(), "grok-4-7") == {"Grok Build|xhigh"}

    def reharness(dataset):
        for model in dataset["models"]:
            if model["id"] == "qwen-4-max":
                model["harness"] = "OpenCode"

    assert config(payload(reharness), "qwen-4-max") == {"OpenCode|xhigh"}


def test_null_values_are_omitted_and_named_unavailable_never_zero():
    out = native(payload())
    costless = [
        r
        for r in out
        if r["dimensions"]["category"] != "overall"
        and "cost_per_task" in r["source_metadata"]["unavailable_metrics"]
    ]
    assert len(costless) == 17
    assert all("cost_per_task" not in r["metrics"] for r in costless)
    (muse,) = [
        r
        for r in out
        if r["source_identifier"] == "muse-wonder-full"
        and r["dimensions"]["category"] == "overall"
    ]
    assert muse["source_metadata"]["unavailable_metrics"] == ["cost_per_task"]
    assert "cost_per_task" not in muse["metrics"]


def test_specialists_use_their_partner_category_and_have_no_overall_row():
    specialists = {"kimi-k3-1-pro-abliterated", "deepseek-4-1-flash-abliterated", "hinoki-ho1"}
    out = [r for r in native(payload()) if r["source_identifier"] in specialists]
    assert len(out) == 3
    assert {r["dimensions"]["category"] for r in out} == {"arithmetic"}
    assert all(
        r["source_metadata"]["unavailable_metrics"]
        == ["cost_per_task", "tokens_per_task"]
        for r in out
    )


def test_row_digest_ignores_array_order_and_integral_float_spelling():
    def reorder(dataset):
        dataset["results"].reverse()
        dataset["models"].reverse()
        result(dataset, "claude-fable-5-2", "fleet")["tasks"] = 18
        result(dataset, "claude-fable-5-2", "fleet")["score"] = 9.29

    def digests(data):
        return {
            (r["source_identifier"], r["dimensions"]["category"]): r["source_metadata"][
                "row_semantic_hash"
            ]
            for r in native(data)
        }

    assert digests(payload()) == digests(payload(reorder))


@pytest.mark.parametrize(
    ("form", "unit", "value", "message"),
    [
        ("monetary", "usd", -0.01, "negative quantity"),
        ("ratio", "output_tokens_per_task", -1, "negative quantity"),
        ("score", "percent", 100.5, "invalid GDPx percentage"),
        ("score", "percent", -1, "invalid GDPx percentage"),
    ],
)
def test_shared_value_validator_rejects_negative_money_and_bad_percentages(
    form, unit, value, message
):
    from core.benchmark_metric_store import numeric_value

    definition = SimpleNamespace(
        value_kind="float",
        quantity_form=form,
        unit_reference_id=unit,
        source_id="gdpx",
    )
    with pytest.raises(ValueError, match=message):
        numeric_value(definition, value)
    assert numeric_value(definition, 0) == {"float_value": 0.0}


# --- PostgreSQL scenarios --------------------------------------------------------


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_first_poll_stores_full_publication_unmapped_and_reports_393_of_393():
    from core.models import CollectionObservation, MetricValue

    target = contract()
    run = persist(target, "1", payload())
    assert run.status == "success"
    assert (run.selected_count, run.success_count) == (EXPECTED, EXPECTED)
    stored = rows(run)
    assert stored.count() == EXPECTED
    assert stored.filter(category_key="overall").count() == OVERALL
    assert stored.exclude(category_key="overall").count() == RESULTS
    assert not stored.filter(mapping__isnull=False).exists()
    assert set(stored.values_list("published_date", flat=True)) == {date(2026, 11, 25)}
    assert set(stored.values_list("source_record_date", flat=True)) == {
        date(2026, 11, 25)
    }
    assert set(stored.values_list("publication_precision", flat=True)) == {"date"}
    assert not stored.filter(supersedes_observation__isnull=False).exists()
    cell = stored.get(source_identifier="claude-fable-5-2", category_key="fleet")
    assert cell.config_key == "Claude Code|max"
    assert cell.coordinate_key == payload()["partners"]["fleet"]["domain"]
    values = {v.source_metric.metric_key: v for v in cell.values.all()}
    assert values["score"].float_value == 9.29
    assert values["tasks"].integer_value == 18
    assert values["cost_per_task"].float_value == 20.2
    assert values["score"].as_of_date == date(2026, 11, 25)
    (marker,) = CollectionObservation.objects.filter(observation_kind="publication_marker")
    assert marker.run_id == run.pk
    assert marker.published_date == date(2026, 11, 25)
    assert marker.source_identifier == "gdpx:publication"
    assert marker.provider_revision == payload()["version_probe"]["label"]
    assert marker.payload_sha256 == payload()["version_probe"]["task_totals_sha256"]
    assert check(run).source_record_date == date(2026, 11, 25)
    assert check(run).payload_sha256 == payload()["dataset_sha256"]
    assert check(run).mapping_id is None
    assert links(run).count() == EXPECTED
    assert MetricValue.objects.filter(observation__run=run).count() > 0


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_null_cost_cells_store_unavailable_gaps_and_no_zero_values():
    from core.models import CollectionMetricGap, MetricValue

    run = persist(contract(), "1", payload())
    gaps = CollectionMetricGap.objects.filter(observation__run=run)
    cost = gaps.filter(source_metric__metric_key="cost_per_task")
    assert cost.exclude(observation__category_key="overall").count() == 17
    assert set(
        cost.filter(observation__category_key="overall").values_list(
            "observation__source_identifier", flat=True
        )
    ) == {"muse-wonder-full"}
    assert set(gaps.values_list("reason_code", flat=True)) == {"source_value_unavailable"}
    assert gaps.filter(source_metric__metric_key="tokens_per_task").count() == 3
    # Overall rows publish no score, so no score gap is invented for them.
    assert not gaps.filter(source_metric__metric_key="score").exists()
    zero_costs = sum(
        1
        for r in payload()["dataset"]["results"]
        if r["costPerTask"] == 0
    )
    assert (
        MetricValue.objects.filter(
            observation__run=run,
            source_metric__metric_key="cost_per_task",
            float_value=0,
        ).count()
        == zero_costs
    )
    assert not MetricValue.objects.filter(
        observation__metric_gaps__source_metric__metric_key="cost_per_task",
        source_metric__metric_key="cost_per_task",
    ).exists()


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_unchanged_repoll_under_new_chunk_writes_nothing_and_reports_393_reused():
    from core.models import CollectionObservation, MetricValue

    target = contract()
    first = persist(target, "1", payload())
    clocks = dict(rows(first).values_list("pk", "observed_at"))
    values = MetricValue.objects.count()

    def reorder(dataset):
        dataset["results"].reverse()

    redeployed = payload(reorder)
    redeployed["dataset_chunk"] = "/_next/static/immutable/chunks/zzzzzzzzzzzzz.js"
    second = persist(target, "2", redeployed)
    assert second.status == "success"
    assert (second.selected_count, second.success_count) == (EXPECTED, EXPECTED)
    assert not rows(second).exists()
    assert MetricValue.objects.count() == values
    assert dict(rows(first).values_list("pk", "observed_at")) == clocks
    assert links(second).count() == EXPECTED
    assert set(links(second).values_list("input_observation__run_id", flat=True)) == {
        first.pk
    }
    assert check(second).revision_conflict is None
    assert CollectionObservation.objects.filter(
        observation_kind="publication_marker"
    ).count() == 1


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_lowered_score_under_newer_date_supersedes_only_that_cell():
    from core.models import CollectionObservation, MetricValue

    target = contract()
    first = persist(target, "1", payload())
    values = MetricValue.objects.count()

    def lower(dataset):
        result(dataset, "claude-haiku-5-5", "fleet")["score"] -= 1

    second = persist(target, "2", payload(lower, updated="2026-11-26"))
    assert second.status == "success"
    assert second.success_count == second.selected_count == EXPECTED
    (changed,) = rows(second)
    prior = rows(first).get(source_identifier="claude-haiku-5-5", category_key="fleet")
    assert changed.source_identifier == "claude-haiku-5-5"
    assert changed.supersedes_observation_id == prior.pk
    assert changed.published_date == date(2026, 11, 26)
    assert changed.revision_conflict is None
    assert (
        changed.values.get(source_metric__metric_key="score").float_value
        == prior.values.get(source_metric__metric_key="score").float_value - 1
    )
    assert MetricValue.objects.count() == values + changed.values.count()
    referenced = links(second).values_list("input_observation__run_id", flat=True)
    assert list(referenced).count(first.pk) == EXPECTED - 1
    assert list(referenced).count(second.pk) == 1
    dates = CollectionObservation.objects.filter(
        observation_kind="publication_marker"
    ).values_list("published_date", flat=True)
    assert sorted(dates) == [date(2026, 11, 25), date(2026, 11, 26)]


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_changed_row_under_same_date_is_a_flagged_revision_conflict():
    target = contract()
    first = persist(target, "1", payload())

    def change(dataset):
        result(dataset, "claude-haiku-5-5", "fleet")["partialScore"] += 0.5

    second = persist(target, "2", payload(change))
    (changed,) = rows(second)
    assert changed.revision_conflict is True
    assert changed.supersedes_observation_id == (
        rows(first).get(source_identifier="claude-haiku-5-5", category_key="fleet").pk
    )
    assert check(second).revision_conflict is True
    assert archived_check(second)["revision_anomaly"] == "same_update_different_body"
    assert second.status == "success"


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_older_dataset_after_newer_records_a_check_and_keeps_the_selection():
    from core.benchmark_opencode import selected_identity_rows
    from core.models import CollectionObservation, MetricValue

    target = contract()
    newer = persist(target, "1", payload(updated="2026-11-26"))
    selection = {k: o.pk for k, o in selected_identity_rows(target, "gdpx").items()}
    values = MetricValue.objects.count()
    older = persist(target, "2", payload())
    assert not rows(older).exists()
    assert MetricValue.objects.count() == values
    assert check(older).source_record_date == date(2026, 11, 25)
    assert not links(older).exists()
    assert archived_check(older)["revision_anomaly"] == "older_than_stored"
    assert older.status == "partial" and older.success_count == 0
    assert {
        k: o.pk for k, o in selected_identity_rows(target, "gdpx").items()
    } == selection
    assert set(selection.values()) == set(rows(newer).values_list("pk", flat=True))
    assert CollectionObservation.objects.filter(
        observation_kind="publication_marker"
    ).count() == 1


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_model_absent_from_newer_dataset_keeps_prior_rows_and_run_succeeds():
    from core.models import MetricValue

    target = contract()
    first = persist(target, "1", payload())
    values = MetricValue.objects.count()

    def remove(dataset):
        dataset["models"] = [m for m in dataset["models"] if m["id"] != "muse-wonder"]
        dataset["results"] = [
            r for r in dataset["results"] if r["modelId"] != "muse-wonder"
        ]
        del dataset["overall"]["muse-wonder"]

    smaller = payload(remove, updated="2026-11-26")
    removed = EXPECTED - smaller["expected_observation_count"]
    assert removed > 1
    second = persist(target, "2", smaller)
    assert second.status == "success"
    assert second.selected_count == second.success_count == EXPECTED - removed
    assert not rows(second).exists()
    assert MetricValue.objects.count() == values
    assert rows(first).filter(source_identifier="muse-wonder").count() == removed
    assert not links(second).filter(
        input_observation__source_identifier="muse-wonder"
    ).exists()
    absent = archived_check(second)["absent_rows"]
    assert len(absent) == removed
    assert all(label.startswith("muse-wonder|") for label in absent)


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_partially_committed_publication_is_partial_without_mappings(monkeypatch):
    import core.benchmark_metric_store as store

    original = store.commit_prepared_rows

    def faulty(run, prepared, **kwargs):
        return original(run, prepared[:200], **kwargs)

    monkeypatch.setattr(store, "commit_prepared_rows", faulty)
    run = persist(contract(), "1", payload())
    assert run.selected_count == EXPECTED
    assert run.success_count == 200
    assert run.status == "partial"
    assert rows(run).count() == 200


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_prior_gdpx_rows_are_found_without_mappings():
    from core.benchmark_opencode import selected_identity_rows

    target = contract()
    run = persist(target, "1", payload())
    current = selected_identity_rows(target, "gdpx")
    assert len(current) == EXPECTED
    assert {o.mapping_id for o in current.values()} == {None}
    assert {o.pk for o in current.values()} == set(
        rows(run).values_list("pk", flat=True)
    )
    cell = rows(run).get(source_identifier="claude-fable-5-2", category_key="fleet")
    assert current["claude-fable-5-2|fleet|Claude Code|max"].pk == cell.pk


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_opencode_rows_still_require_their_reviewed_mapping():
    from core.benchmark_metric_store import persist_source, prepare_rows
    from core.benchmark_opencode import prepare_revisions, record_endpoint_checks
    from tests.test_benchmark_opencode import configured, endpoint, read

    target = configured()
    run = persist_source(target, "opencode", "f" * 64, read(endpoint()))
    assert run.status == "success"
    unmapped = {
        "source_identifier": "other/model",
        "status": "ok",
        "updated_at": "2026-10-07T12:44:18+00:00",
        "body_sha256": "0" * 64,
        "row_references": {},
    }
    with pytest.raises(ValueError, match="endpoint mapping is missing"):
        record_endpoint_checks(run, [unmapped], target)
    data = read(endpoint())
    prepared = prepare_rows(target, "opencode", data)
    for observation, _ in prepared:
        observation["source_identifier"] = "other/model"
    data["endpoint_checks"][0]["source_identifier"] = "other/model"
    with pytest.raises(ValueError, match="OpenCode endpoint differs from reviewed mapping"):
        prepare_revisions(target, prepared, data)


# --- headline from stored rows (R15) ---------------------------------------------


def computed_headlines(data):
    """The U2 computation over a payload's non-specialist per-partner scores."""
    from core.benchmark_gdpx import headline_scores

    dataset = data["dataset"]
    specialists = {m["id"] for m in dataset["models"] if "specialist" in m}
    domains = {pid: entry["domain"] for pid, entry in data["partners"].items()}
    return headline_scores(
        (
            (r["modelId"], r["partnerId"], r["score"])
            for r in dataset["results"]
            if r["modelId"] not in specialists
        ),
        domains,
    )


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_stored_headline_equals_reader_computation_and_site_values():
    from core.benchmark_gdpx import stored_headline_scores

    data = payload()
    run = persist(contract(), "1", data)
    assert run.status == "success"
    scores = stored_headline_scores(run.job.contract)
    expected = computed_headlines(data)
    assert len(expected) == OVERALL
    assert scores == pytest.approx(expected, abs=1e-9)
    shown = {row["model_id"]: row["published"] for row in data["headline_check"]}
    assert {m: round(scores[m], 1) for m in shown} == shown
    assert sorted(shown.values(), reverse=True)[:3] == [19.3, 16.4, 11.9]
    assert round(scores["gpt-6-2-astra"], 4) == 19.2612
    # Specialists are stored but, as on the site, carry no headline.
    for specialist in ("hinoki-ho1", "kimi-k3-1-pro-abliterated"):
        assert rows(run).filter(source_identifier=specialist).exists()
        assert specialist not in scores


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_stored_headline_uses_only_the_latest_revision_after_supersession():
    from core.benchmark_gdpx import stored_headline_scores

    target = contract()
    persist(target, "1", payload())
    before = stored_headline_scores(target)

    def lower(dataset):
        result(dataset, "claude-haiku-5-5", "fleet")["score"] -= 1

    newer = payload(lower, updated="2026-11-26")
    persist(target, "2", newer)
    after = stored_headline_scores(target)
    assert after == pytest.approx(computed_headlines(newer), abs=1e-9)
    assert after["claude-haiku-5-5"] < before["claude-haiku-5-5"]
    assert {k: v for k, v in after.items() if k != "claude-haiku-5-5"} == (
        pytest.approx({k: v for k, v in before.items() if k != "claude-haiku-5-5"})
    )
    # An older publication polled afterwards never replaces the selection.
    persist(target, "3", payload())
    assert stored_headline_scores(target) == pytest.approx(after, abs=1e-9)


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_model_without_stored_rows_has_no_headline_not_zero():
    from core.benchmark_gdpx import stored_headline_scores
    from core.benchmark_opencode import selected_identity_rows

    target = contract()
    assert stored_headline_scores(target) == {}
    persist(target, "1", payload())
    assert "no-such-model" not in stored_headline_scores(target)

    def remove(dataset):
        dataset["models"] = [m for m in dataset["models"] if m["id"] != "muse-wonder"]
        dataset["results"] = [
            r for r in dataset["results"] if r["modelId"] != "muse-wonder"
        ]
        del dataset["overall"]["muse-wonder"]

    smaller = payload(remove, updated="2026-11-26")
    persist(target, "2", smaller)
    # Its older rows stay stored and selected, but the latest publication omits it.
    assert any(
        o.source_identifier == "muse-wonder"
        for o in selected_identity_rows(target, "gdpx").values()
    )
    scores = stored_headline_scores(target)
    assert "muse-wonder" not in scores
    assert scores == pytest.approx(computed_headlines(smaller), abs=1e-9)

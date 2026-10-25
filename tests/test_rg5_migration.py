"""Populate every selected owner before the reference migrations run."""

import importlib

import pytest
from django.db import IntegrityError, ProgrammingError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]
BEFORE = ("core", "0160_rg4_remove_superseded_storage")
AFTER = ("core", "0166_rg5_reference_source_guards")
RETIRED = ("core", "0168_rg5_remove_superseded_storage")


@pytest.mark.parametrize("migration_rehearsal_schema", [BEFORE], indirect=True)
def test_populated_rg5_maps_all_24_columns_without_changing_evidence(
    migration_rehearsal_schema,
):
    executor = MigrationExecutor(connection)
    old = executor.loader.project_state([BEFORE]).apps

    def model(name):
        return old.get_model("core", name)

    for source in ("x", "hf"):
        model("DataSource").objects.get_or_create(
            pk=source, defaults={"name": source, "source_type": "social"}
        )
    model("TimeZone").objects.get_or_create(pk="UTC")
    account = model("Account").objects.create(
        data_source_id="x",
        author_id="rg5-history",
        external_identifier="rg5-history",
        normalized_identifier="rg5-history",
    )
    x_fields = {
        "verified_type": "",
        "affiliate_label_url_type": "DeepLink",
        "affiliate_label_user_label_display_type": "Badge",
        "affiliate_label_user_label_type": "BusinessLabel",
        "identity_profile_label_url_type": "DeepLink",
        "identity_profile_label_user_label_display_type": "Badge",
        "identity_profile_label_user_label_type": "AutomatedLabel",
    }
    model("XAccountDetail").objects.create(account=account, **x_fields)
    profile = model("AccountProfileSnapshot").objects.create(
        account=account,
        profile_hash="a" * 64,
        first_observed_at=timezone.now(),
        last_observed_at=timezone.now(),
        first_source_kind="post",
        verified_type="Business",
        affiliate_label_type="BusinessLabel",
        affiliate_display_type="Badge",
        present_fields=list(x_fields),
    )
    model("Post").objects.create(
        tweet_id="rg5-history", author=account, author_verified_type="Government"
    )
    product = model("Product").objects.create(
        repo_id="rg5/history",
        type="llm-model",
        gated="False",
        library_name="transformers",
        pipeline_tag="text-generation",
        raw={"gated": False},
    )
    other = model("Product").objects.create(
        repo_id="rg5/other",
        type="llm-model",
        library_name="",
        pipeline_tag="",
        raw={"library_name": "", "pipeline_tag": ""},
    )
    taxonomy = model("TaxonomyVersion").objects.create(
        version_hash="b" * 64, snapshot={"unchanged": True}, reviewed_by="fixture"
    )
    model("ProductRelationship").objects.create(
        taxonomy_version=taxonomy,
        parent_product=product,
        child_product=other,
        relationship_type="new_version",
        evidence={"unchanged": True},
        reviewed_by="fixture",
    )
    subject = model("MeasurementSubject").objects.create(
        subject_kind="product", product=product
    )
    mapping = model("SourceSubjectMapping").objects.create(
        purpose="catalog",
        source_id="hf",
        subject=subject,
        source_subject_kind="repository",
        identifier_scope="",
        external_identifier="rg5/history",
        normalized_identifier="rg5/history",
        mapping_hash="c" * 64,
        evidence_url="https://huggingface.co/rg5/history",
        reviewed_by="fixture",
    )
    job = model("CollectionJob").objects.create(
        job_key="rg5-history",
        source_id="hf",
        purpose="catalog",
        operation="hf_catalog",
        mode="historical",
        definition={
            "version": 1,
            "scope": {},
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 1, "bytes": 1000, "seconds": 10, "items": 1},
        },
        definition_sha256="d" * 64,
    )
    run = model("CollectionRun").objects.create(
        job=job, status="pending", ingestion_key="e" * 64
    )
    observation = model("CollectionObservation").objects.create(
        run=run,
        source_identifier="rg5/history",
        source_subject_kind="repository",
        observation_key="f" * 64,
        listing={"gated": False, "library_name": "transformers"},
    )
    model("CollectionResourceSnapshot").objects.create(
        observation=observation,
        resource_kind="repository",
        native_identifier="rg5/history",
        gated_status="public",
        library_name="transformers",
        pipeline_tag="text-generation",
    )
    model("CollectionJobTarget").objects.create(
        job=job,
        target_key="history",
        ordinal=0,
        target_kind="product",
        target_role="selected",
        resolution_state="resolved",
        subject=subject,
        mapping=mapping,
        identifier_scope="",
    )
    metric_type, _ = model("MetricType").objects.get_or_create(
        pk="downloads", defaults={"name": "Downloads"}
    )
    unit, _ = model("MeasurementUnit").objects.get_or_create(pk="downloads")
    metric = model("SourceMetric").objects.create(
        source_id="hf",
        metric_type=metric_type,
        metric_key="downloads",
        version=1,
        name="Downloads",
        unit_reference=unit,
        value_kind="integer",
        quantity_form="count",
        measurement_kind="state",
    )
    value = model("MetricValue").objects.create(
        observation=observation,
        source_metric=metric,
        integer_value=4_000_000_000,
        source_timezone="UTC",
    )
    correction = model("CollectionCorrection").objects.create(
        observation=observation,
        metric_value=value,
        correction_kind="timing",
        policy_version="fixture-v1",
        actor=model("Actor").objects.first(),
        reason_code="fixture",
        before_source_timezone="unknown",
        after_source_timezone="UTC",
    )
    preserved = (
        profile.profile_hash,
        mapping.mapping_hash,
        taxonomy.version_hash,
        correction.pk,
        observation.listing,
    )
    executor.migrate([AFTER])
    current = executor.loader.project_state([AFTER]).apps
    product_domains = importlib.import_module(
        "core.migrations.0163_rg5_product_references"
    ).DOMAINS
    account_domains = importlib.import_module(
        "core.migrations.0164_rg5_account_classification_references"
    ).DOMAINS
    with connection.cursor() as cursor:
        for domain in product_domains:
            expected = f"o.{domain['old']}"
            if domain.get("source_sql"):
                expected = f"NULLIF(o.{domain['old']}, '')"
            if domain.get("gating"):
                expected = f"CASE o.{domain['old']} WHEN 'False' THEN 'public' WHEN 'True' THEN 'gated' ELSE o.{domain['old']} END"
            cursor.execute(
                f"SELECT count(*) FROM {domain['table']} o LEFT JOIN {domain['catalogue']} c ON c.id=o.{domain['new']} WHERE c.code IS DISTINCT FROM ({expected})"
            )
            assert cursor.fetchone() == (0,)
        for table, field, catalogue, _ in account_domains:
            cursor.execute(
                f"SELECT count(*) FROM {table} o JOIN {catalogue} c ON c.id=o.{field}_id WHERE c.code=o.{field} AND c.data_source_id='x'"
            )
            assert cursor.fetchone() == (1,)
        for table in ("source_subject_mappings", "collection_job_targets"):
            cursor.execute(
                f"SELECT c.code,c.data_source_id,c.subject_kind FROM {table} o JOIN source_identifier_namespaces c ON c.id=o.identifier_scope_id"
            )
            assert cursor.fetchone() == ("", "hf", "repository")
        cursor.execute("SELECT source_timezone_id,integer_value FROM metric_values")
        assert cursor.fetchone() == ("UTC", 4_000_000_000)
        cursor.execute(
            "SELECT before_source_timezone_id,after_source_timezone_id FROM collection_corrections"
        )
        assert cursor.fetchone() == (None, "UTC")
        cursor.execute(
            "SELECT library_name,pipeline_tag,library_name_id,pipeline_tag_id "
            "FROM products WHERE repo_id='rg5/other'"
        )
        assert cursor.fetchone() == ("", "", None, None)
    assert current.get_model("core", "Product").objects.get(pk=other.pk).raw == {
        "library_name": "",
        "pipeline_tag": "",
    }
    # A restart validates the existing reference and keeps explicit corrections.
    bridge = importlib.import_module("core.migrations._rg5_reference_mapping_v1")
    bridge.install_and_map(connection, **product_domains[2])
    bridge_name = bridge.bridge_name("products", "library_name")
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE products DISABLE TRIGGER {bridge_name}")
    with pytest.raises(RuntimeError, match="Unsafe reference bridge resume"):
        bridge.install_and_map(connection, **product_domains[2])
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE products ENABLE TRIGGER {bridge_name}")
    assert preserved == (
        current.get_model("core", "AccountProfileSnapshot")
        .objects.get(pk=profile.pk)
        .profile_hash,
        current.get_model("core", "SourceSubjectMapping")
        .objects.get(pk=mapping.pk)
        .mapping_hash,
        current.get_model("core", "TaxonomyVersion")
        .objects.get(pk=taxonomy.pk)
        .version_hash,
        current.get_model("core", "CollectionCorrection").objects.get().pk,
        current.get_model("core", "CollectionObservation")
        .objects.get(pk=observation.pk)
        .listing,
    )
    retirement = importlib.import_module("core.migrations._rg5_retirement_v1")
    executor = MigrationExecutor(connection)
    executor.migrate([RETIRED])
    assert executor.recorder.migration_qs.filter(app=RETIRED[0], name=RETIRED[1]).exists()
    with connection.cursor() as cursor:
        for item in retirement.domains():
            cursor.execute(
                "SELECT attname FROM pg_attribute WHERE attrelid=%s::regclass "
                "AND attname=%s AND NOT attisdropped",
                [item["table"], item["old"]],
            )
            assert cursor.fetchone() is None
    with (
        pytest.raises(ProgrammingError),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("SELECT source_timezone FROM metric_values LIMIT 1")
    product_model = current.get_model("core", "Product")
    product_model.objects.filter(pk=other.pk).update(
        library_name_id=product_model.objects.get(pk=product.pk).library_name_id
    )
    assert product_model.objects.get(pk=other.pk).library_name.code == "transformers"
    wrong = current.get_model("core", "SoftwareLibrary").objects.create(
        data_source_id="x", code="other-provider"
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        product_model.objects.filter(pk=other.pk).update(library_name=wrong)
    assert (
        current.get_model("core", "MetricValue").objects.get(pk=value.pk).integer_value
        == 4_000_000_000
    )
    assert (
        current.get_model("core", "CollectionCorrection").objects.get().pk
        == correction.pk
    )
    assert (
        current.get_model("core", "AccountProfileSnapshot")
        .objects.get(pk=profile.pk)
        .profile_hash
        == profile.profile_hash
    )

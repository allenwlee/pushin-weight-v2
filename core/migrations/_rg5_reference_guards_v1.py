"""Frozen source ownership checks retained after the rolling bridges retire."""

import importlib


def install_source_guards(schema_editor):
    products = importlib.import_module("core.migrations.0163_rg5_product_references")
    accounts = importlib.import_module(
        "core.migrations.0164_rg5_account_classification_references"
    )
    namespaces = importlib.import_module(
        "core.migrations.0165_rg5_identifier_namespace_references"
    )
    domains = [d for d in products.DOMAINS if d.get("source_sql")]
    domains += [
        {
            "table": table,
            "new": field + "_id",
            "catalogue": catalogue,
            "source_sql": "'x'" if table == "posts" else accounts.ACCOUNT_SOURCE,
        }
        for table, field, catalogue, _ in accounts.DOMAINS
    ]
    domains += [
        {
            "table": "source_subject_mappings",
            "new": "identifier_scope_id",
            "catalogue": "source_identifier_namespaces",
            "source_sql": "NEW.source_id",
            "kind_sql": "NEW.source_subject_kind",
        },
        {
            "table": "collection_job_targets",
            "new": "identifier_scope_id",
            "catalogue": "source_identifier_namespaces",
            "source_sql": namespaces.TARGET_SOURCE,
            "kind_sql": namespaces.TARGET_KIND,
        },
    ]
    locks = {
        "account_profile_snapshots": "PERFORM 1 FROM accounts WHERE account_key=NEW.account_key FOR SHARE;",
        "x_account_details": "PERFORM 1 FROM accounts WHERE account_key=NEW.account_key FOR SHARE;",
        "collection_resource_snapshots": "PERFORM 1 FROM collection_observations o JOIN collection_runs r ON r.id=o.run_id WHERE o.id=NEW.observation_id FOR SHARE OF o,r;",
        "collection_job_targets": "PERFORM 1 FROM source_subject_mappings WHERE id=NEW.mapping_id FOR SHARE; PERFORM 1 FROM collection_observations o JOIN collection_runs r ON r.id=o.run_id WHERE o.id=NEW.evidence_observation_id FOR SHARE OF o,r;",
    }
    grouped = {}
    for domain in domains:
        grouped.setdefault(domain["table"], []).append(domain)
    for table, fields in grouped.items():
        body = [locks.get(table, "")]
        for field in fields:
            kind = (
                f" AND subject_kind=({field['kind_sql']})"
                if field.get("kind_sql")
                else ""
            )
            body.append(f"""
              IF NEW.{field["new"]} IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM {field["catalogue"]} WHERE id=NEW.{field["new"]}
                AND data_source_id=({field["source_sql"]}) {kind}
              ) THEN
                RAISE EXCEPTION 'Invalid or cross-source {table}.{field["new"]}' USING ERRCODE='23514';
              END IF;
            """)
        name = "pw_rg5_source_" + table
        schema_editor.execute(f"""
          CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN {" ".join(body)} RETURN NEW; END $$;
          CREATE TRIGGER {name} BEFORE INSERT OR UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION {name}();
        """)
    schema_editor.execute(PARENT_GUARDS)


PARENT_GUARDS = """
CREATE FUNCTION pw_rg5_reference_parent_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE previous_source text; next_source text;
BEGIN
  IF TG_TABLE_NAME='accounts' THEN
    IF NEW.data_source_id IS DISTINCT FROM OLD.data_source_id AND EXISTS (
      SELECT 1 FROM account_profile_snapshots WHERE account_key=OLD.account_key
      AND (verified_type_id IS NOT NULL OR affiliate_label_type_id IS NOT NULL OR affiliate_display_type_id IS NOT NULL)
    ) THEN
      RAISE EXCEPTION 'Account source is pinned by profile references' USING ERRCODE='23514';
    END IF;
  ELSIF TG_TABLE_NAME='source_subject_mappings' THEN
    IF ROW(NEW.source_id,NEW.source_subject_kind) IS DISTINCT FROM ROW(OLD.source_id,OLD.source_subject_kind)
      AND EXISTS (SELECT 1 FROM collection_job_targets WHERE mapping_id=OLD.id AND identifier_scope_id IS NOT NULL)
    THEN
      RAISE EXCEPTION 'Mapping source/kind is pinned by job targets' USING ERRCODE='23514';
    END IF;
  ELSIF TG_TABLE_NAME='collection_runs' THEN
    SELECT source_id INTO previous_source FROM collection_jobs WHERE id=OLD.job_id;
    SELECT source_id INTO next_source FROM collection_jobs WHERE id=NEW.job_id;
    IF previous_source IS DISTINCT FROM next_source AND (
      EXISTS (SELECT 1 FROM collection_observations o JOIN collection_resource_snapshots s ON s.observation_id=o.id
              WHERE o.run_id=OLD.id AND (s.library_name_id IS NOT NULL OR s.pipeline_tag_id IS NOT NULL))
      OR EXISTS (SELECT 1 FROM collection_observations o JOIN collection_job_targets t ON t.evidence_observation_id=o.id
                 WHERE o.run_id=OLD.id AND t.identifier_scope_id IS NOT NULL)
    ) THEN
      RAISE EXCEPTION 'Run source is pinned by resource/namespace references' USING ERRCODE='23514';
    END IF;
  ELSIF TG_TABLE_NAME='collection_observations' THEN
    SELECT j.source_id INTO previous_source FROM collection_runs r JOIN collection_jobs j ON j.id=r.job_id WHERE r.id=OLD.run_id;
    SELECT j.source_id INTO next_source FROM collection_runs r JOIN collection_jobs j ON j.id=r.job_id WHERE r.id=NEW.run_id;
    IF previous_source IS DISTINCT FROM next_source AND EXISTS (
      SELECT 1 FROM collection_resource_snapshots WHERE observation_id=OLD.id
      AND (library_name_id IS NOT NULL OR pipeline_tag_id IS NOT NULL)
    ) OR (previous_source IS DISTINCT FROM next_source OR NEW.source_subject_kind IS DISTINCT FROM OLD.source_subject_kind)
      AND EXISTS (SELECT 1 FROM collection_job_targets WHERE evidence_observation_id=OLD.id AND identifier_scope_id IS NOT NULL)
    THEN
      RAISE EXCEPTION 'Observation source/kind is pinned by references' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_rg5_reference_parent_guard BEFORE UPDATE OF data_source_id ON accounts
  FOR EACH ROW EXECUTE FUNCTION pw_rg5_reference_parent_guard();
CREATE TRIGGER pw_rg5_reference_parent_guard BEFORE UPDATE OF source_id,source_subject_kind ON source_subject_mappings
  FOR EACH ROW EXECUTE FUNCTION pw_rg5_reference_parent_guard();
CREATE TRIGGER pw_rg5_reference_parent_guard BEFORE UPDATE OF job_id ON collection_runs
  FOR EACH ROW EXECUTE FUNCTION pw_rg5_reference_parent_guard();
CREATE TRIGGER pw_rg5_reference_parent_guard BEFORE UPDATE OF run_id,source_subject_kind ON collection_observations
  FOR EACH ROW EXECUTE FUNCTION pw_rg5_reference_parent_guard();
"""

"""Keep serving-safe category claims bound to the retained source packet."""
from django.db import migrations

FORWARD = r"""
CREATE FUNCTION pw_pulse_canonical_json(value jsonb) RETURNS text
LANGUAGE plpgsql IMMUTABLE STRICT SET search_path = pg_catalog, public AS $$
DECLARE result text;
BEGIN
    CASE jsonb_typeof(value)
    WHEN 'object' THEN
        SELECT '{' || COALESCE(string_agg(to_json(key)::text || ':' || public.pw_pulse_canonical_json(item), ','
                                           ORDER BY key COLLATE "C"), '') || '}'
          INTO result FROM jsonb_each(value) AS fields(key, item);
    WHEN 'array' THEN
        SELECT '[' || COALESCE(string_agg(public.pw_pulse_canonical_json(item), ',' ORDER BY ordinal), '') || ']'
          INTO result FROM jsonb_array_elements(value) WITH ORDINALITY AS elements(item, ordinal);
    ELSE result := value::text;
    END CASE;
    RETURN result;
END $$;
CREATE FUNCTION pw_pulse_category_evidence_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE
    packet jsonb;
    evidence bytea;
    archive_hash text;
    archive_size bigint;
    archive_kind text;
    archive_encoding text;
    source_post text;
    source_observation bigint;
    category text;
BEGIN
    IF NEW.scope_key NOT LIKE 'pulse-category-v1:%' THEN
        RETURN NEW;
    END IF;
    SELECT a.body, a.content_sha256, a.byte_count, a.capture_kind, a.encoding,
           s.post_id, s.collection_observation_id
      INTO evidence, archive_hash, archive_size, archive_kind, archive_encoding,
           source_post, source_observation
      FROM public.collection_evidence_archives a
      JOIN public.event_dossier_sources s ON s.id = NEW.event_dossier_source_id
     WHERE a.id = NEW.source_archive_id;
    IF evidence IS NULL OR octet_length(evidence) > 65536 OR archive_size <> octet_length(evidence)
       OR archive_hash <> encode(sha256(evidence), 'hex')
       OR archive_kind <> 'product_release_intake' OR archive_encoding <> 'selected-json-canonical-v1'
       OR NOT (convert_from(evidence, 'UTF8') IS JSON OBJECT WITH UNIQUE KEYS) THEN
        RAISE EXCEPTION 'Invalid Pulse category source' USING ERRCODE='23514';
    END IF;
    packet := convert_from(evidence, 'UTF8')::jsonb;
    category := packet->'finding'->>'category';
    IF public.pw_pulse_canonical_json(packet) IS DISTINCT FROM convert_from(evidence, 'UTF8')
       OR jsonb_typeof(packet) IS DISTINCT FROM 'object'
       OR (SELECT count(*) FROM jsonb_object_keys(packet)) <> 6
       OR packet->>'schema' IS DISTINCT FROM 'pulse-release-intake-v1'
       OR jsonb_typeof(packet->'finding') IS DISTINCT FROM 'object'
       OR NOT (packet->'finding' ? 'category')
       OR jsonb_typeof(packet->'source') IS DISTINCT FROM 'object'
       OR (SELECT count(*) FROM jsonb_object_keys(packet->'source')) <> 2
       OR NOT (packet->'source' ?& ARRAY['kind','id'])
       OR jsonb_typeof(packet->'finding'->'finding_key') IS DISTINCT FROM 'string'
       OR COALESCE(packet->'finding'->>'finding_key', '') !~ '^[0-9a-f]{64}$'
       OR jsonb_typeof(packet->'revision_id') IS DISTINCT FROM 'string'
       OR COALESCE(packet->>'revision_id', '') !~ '^[0-9a-f]{64}$'
       OR jsonb_typeof(packet->'content_fingerprint') IS DISTINCT FROM 'string'
       OR COALESCE(packet->>'content_fingerprint', '') !~ '^[0-9a-f]{64}$'
       OR jsonb_typeof(packet->'extraction_version') IS DISTINCT FROM 'string'
       OR btrim(COALESCE(packet->>'extraction_version', ''),
            chr(9)||chr(10)||chr(11)||chr(12)||chr(13)||chr(28)||chr(29)||chr(30)||chr(31)||chr(32)||
            chr(133)||chr(160)||chr(5760)||chr(8192)||chr(8193)||chr(8194)||chr(8195)||chr(8196)||
            chr(8197)||chr(8198)||chr(8199)||chr(8200)||chr(8201)||chr(8202)||chr(8232)||chr(8233)||
            chr(8239)||chr(8287)||chr(12288)) = ''
       OR jsonb_typeof(packet->'finding'->'category') NOT IN ('string', 'null')
       OR NEW.scope_key IS DISTINCT FROM 'pulse-category-v1:' || (packet->'finding'->>'finding_key')
       OR NEW.extraction_version IS DISTINCT FROM 'pulse-classified-findings-v1:' || (packet->>'revision_id')
       OR NEW.assertion_text IS DISTINCT FROM COALESCE(category, 'unknown')
       OR (category IS NOT NULL AND category NOT IN ('model-llm','model-other','agent','harness','other'))
       OR NOT COALESCE(((source_post IS NOT NULL AND source_observation IS NULL
                 AND packet->'source'->>'kind' = 'post' AND jsonb_typeof(packet->'source'->'id') = 'string'
                 AND packet->'source'->>'id' = source_post)
            OR (source_post IS NULL AND source_observation IS NOT NULL
                 AND packet->'source'->>'kind' = 'observation' AND jsonb_typeof(packet->'source'->'id') = 'number'
                 AND packet->'source'->>'id' = source_observation::text)), false)
       OR NOT EXISTS (SELECT 1 FROM public.event_claim_kinds k
                      WHERE k.id=NEW.claim_kind_id AND k.code='release_context') THEN
        RAISE EXCEPTION 'Pulse category does not match source' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
EXCEPTION WHEN character_not_in_repertoire OR invalid_text_representation OR program_limit_exceeded THEN
    RAISE EXCEPTION 'Invalid Pulse category source' USING ERRCODE='23514';
END $$;
CREATE TRIGGER pw_pulse_category_evidence_guard BEFORE INSERT OR UPDATE ON event_dossier_claims
FOR EACH ROW EXECUTE FUNCTION pw_pulse_category_evidence_guard();
"""
REVERSE = """
DROP TRIGGER pw_pulse_category_evidence_guard ON event_dossier_claims;
DROP FUNCTION pw_pulse_category_evidence_guard();
DROP FUNCTION IF EXISTS pw_pulse_canonical_json(jsonb);
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0240_pending_publication_admission_index")]
    operations = [migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
                  migrations.RunSQL(FORWARD, REVERSE)]

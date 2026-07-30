"""Plan 2026-07-30-002 U4 — brand keyword primary purity seed.

Primary demotion per R15–R16. Idempotent: every UPDATE has a WHERE clause
that checks the current state, so re-running is a no-op for already-pure
rows.

R16 (B1 pure brands — should be is_primary=true):
  - deepseek, qwen, minimax, stepfun, mistral, hunyuan, glm,
    inclusionai, exaone, sakana_ai, nemo_megatron

R15 (demote dirty primaries — should be is_primary=false):
  - `m2.5` (minimax) — model-version specific, not a brand name
  - bare `海螺` (minimax) — too short, collides with the actual product
    name `Hailuo`; keep `Hailuo` + `MiniMax`
  - bare `Mistral` (mistral) — keep `Mistral AI` + `Mixtral` (NOTE: the
    data has `Mistral` as primary=true and `Mixtral` as primary=true;
    per the plan body `Mixtral` stays, only bare `Mistral` is demoted)
  - bare `混元` (hunyuan) — keep `Hunyuan` + `腾讯混元`
  - bare `GLM` (glm) — NOTE: data has no bare `GLM` row; demotion is
    a no-op safety guard in case future rows add one
  - bare `Ling` / bare `Ring` (inclusionai) — keep `InclusionAI`
  - bare `Solar` (upstage) — substring leak fix from earlier work
  - bare `日日新` (sensechat) — keep `SenseChat` + `SenseTime`

This migration is data-only (no schema changes). It runs in a single
transaction; rows touched are <100 so the transaction is cheap.
"""

from django.db import migrations


# Idempotent: each tuple is (brand, pattern) to set is_primary=false.
# The SQL applies the WHERE clause so re-running is a no-op.
DEMOTE_LIST = [
    # R15 — minimax: m2.5 + bare 海螺
    ("minimax", "m2.5"),
    ("minimax", "海螺"),
    # R15 — mistral: bare Mistral (keep Mixtral)
    ("mistral", "Mistral"),
    # R15 — hunyuan: bare 混元 (keep Hunyuan + 腾讯混元)
    ("hunyuan", "混元"),
    # R15 — glm: bare GLM (safety guard; data has no such row today)
    ("glm", "GLM"),
    # R15 — inclusionai: bare Ling, bare Ring (keep InclusionAI)
    ("inclusionai", "Ling"),
    ("inclusionai", "Ring"),
    # Earlier-work substring leak fix: bare Solar collides with everyday
    # English ("solar wind"). Keep `Solar Pro` / `Solar LLM`.
    ("upstage", "Solar"),
    # R15 — sensechat: bare 日日新 (keep SenseChat + SenseTime)
    ("sensechat", "日日新"),
]


def _demote_dirty_primarys(apps, schema_editor):
    """Idempotent: is_primary=false WHERE (brand, pattern) IN DEMOTE_LIST AND is_primary=true."""
    from django.db import connection

    if schema_editor.connection.vendor != "postgresql":
        return

    if not DEMOTE_LIST:
        return

    with connection.cursor() as cur:
        # Build a CTE of demote targets via VALUES, then UPDATE ... FROM
        # join. Portable across psycopg2 and psycopg3 (which differ on
        # how they bind tuple-in-IN parameters).
        values_sql = ",".join(["(%s,%s)"] * len(DEMOTE_LIST))
        flat_params = []
        for b, p in DEMOTE_LIST:
            flat_params.extend([b, p])
        cur.execute(
            f"""
            WITH targets(brand_id, pattern) AS (
              VALUES {values_sql}
            )
            UPDATE brand_keywords bk
            SET is_primary = false
            FROM targets t
            WHERE bk.is_primary = true
              AND bk.brand_id = t.brand_id
              AND bk.pattern = t.pattern
            """,
            flat_params,
        )
        print(f"U4 purity seed: demoted {cur.rowcount} dirty-primary rows")


def _noop_reverse(apps, schema_editor):
    """Reverse migration: do nothing. The demotion is a one-way purity
    change; reversing would re-promote dirty primaries."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_chunked_backfill"),
    ]

    operations = [
        migrations.RunPython(_demote_dirty_primarys, _noop_reverse),
    ]
"""Typed collections resume one logical run across all supported purposes."""

from importlib import import_module
from typing import ClassVar

from django.db import migrations

PREVIOUS = import_module("core.migrations.0101_collection_instruction_guards").GUARDS
PREVIOUS = PREVIOUS[
    PREVIOUS.index(
        "CREATE OR REPLACE FUNCTION collection_run_job_instructions()"
    ) : PREVIOUS.index("CREATE FUNCTION collection_target_seal_guard()")
]
FORWARD = PREVIOUS.replace(
    "IF NOT (\n        (instructions.purpose=",
    "IF instructions.instruction_version=2 THEN\n"
    "        IF NOT ((NEW.status IN ('pending','running','partial','interrupted') AND NEW.completed_at IS NULL)\n"
    "            OR (NEW.status IN ('success','failed','aborted') AND NEW.completed_at IS NOT NULL)) THEN\n"
    "            RAISE EXCEPTION 'typed collection run lifecycle mismatch' USING ERRCODE='23514';\n"
    "        END IF;\n"
    "    ELSIF NOT (\n        (instructions.purpose=",
)


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0106_collection_schedule_data")]
    operations: ClassVar[list] = [migrations.RunSQL(FORWARD, PREVIOUS)]

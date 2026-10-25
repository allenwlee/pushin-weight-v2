"""Keep source ownership enforced independently of temporary scalar bridges."""

from typing import ClassVar

from django.db import migrations

from ._rg5_reference_guards_v1 import install_source_guards


def install(apps, schema_editor):
    install_source_guards(schema_editor)


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [
        ("core", "0165_rg5_identifier_namespace_references")
    ]
    operations: ClassVar[list] = [
        migrations.RunSQL(
            "SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'"
        ),
        migrations.RunPython(install),
    ]

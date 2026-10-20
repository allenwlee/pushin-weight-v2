from typing import ClassVar

import django.db.models.deletion
import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0093_shared_time_zones")]
    operations: ClassVar[list] = [
        migrations.CreateModel(
            name="Language",
            fields=[
                (
                    "code",
                    models.CharField(max_length=8, primary_key=True, serialize=False),
                ),
            ],
            options={
                "db_table": "languages",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("code__regex", "^[a-z]{2,8}$")),
                        name="ck_language_code_grammar",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Locale",
            fields=[
                (
                    "code",
                    models.CharField(max_length=255, primary_key=True, serialize=False),
                ),
                (
                    "language",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="locales",
                        to="core.language",
                    ),
                ),
            ],
            options={
                "db_table": "locales",
                "constraints": [
                    models.UniqueConstraint(
                        django.db.models.functions.text.Lower("code"),
                        name="uq_locale_code_casefold",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("code__regex", "^[a-z]{2,8}(-[A-Za-z0-9]{1,8})*$")
                        ),
                        name="ck_locale_code_grammar",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "language_id",
                                models.Func(
                                    django.db.models.functions.text.Lower("code"),
                                    models.Value("-"),
                                    models.Value(1),
                                    function="split_part",
                                    output_field=models.CharField(),
                                ),
                            )
                        ),
                        name="ck_locale_primary_language",
                    ),
                ],
            },
        ),
    ]

from typing import ClassVar

from django.db import migrations


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [
        ("core", "0224_chatter_source_snapshot_owner"),
        ("core", "0227_post_translation_requested"),
    ]
    operations: ClassVar[list] = []

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("core", "0072_merge_benchmark_main")]
    operations = [migrations.AlterModelTable(name="sourcemetric", table="metrics")]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0054_productverificationproposal_verification_claim_expires_at_and_more")]

    operations = [
        migrations.RemoveConstraint(
            model_name="raretypedecision",
            name="ck_rare_decision_complete_shape",
        ),
        migrations.AddConstraint(
            model_name="raretypedecision",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(status="completed", completed_at__isnull=False)
                    | (~models.Q(status="completed") & models.Q(completed_at__isnull=True))
                ),
                name="ck_rare_decision_complete_shape",
            ),
        ),
    ]

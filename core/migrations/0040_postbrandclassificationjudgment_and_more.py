import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0039_affiliation_candidate_and_integrity_guards'),
    ]

    operations = [
        migrations.CreateModel(
            name='PostBrandClassificationJudgment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('revision_id', models.CharField(max_length=64)),
                ('stage', models.CharField(choices=[('primary', 'Primary'), ('review', 'Review'), ('final', 'Final')], max_length=16)),
                ('canonical_judgment', models.JSONField()),
                ('contract_version', models.CharField(max_length=64)),
                ('taxonomy_version', models.CharField(max_length=64)),
                ('prompt_version', models.CharField(max_length=64)),
                ('model', models.CharField(max_length=256)),
                ('provider_role', models.CharField(max_length=64)),
                ('input_context_fingerprint', models.CharField(max_length=64)),
                ('selector_version', models.CharField(max_length=64)),
                ('validation_state', models.CharField(max_length=32)),
                ('changes_json', models.JSONField(db_default={}, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('brand', models.ForeignKey(db_column='brand_id', on_delete=django.db.models.deletion.PROTECT, related_name='classification_judgments', to='core.brand')),
                ('parent_judgment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='core.postbrandclassificationjudgment')),
                ('post', models.ForeignKey(db_column='post_id', on_delete=django.db.models.deletion.CASCADE, related_name='classification_judgments', to='core.post')),
            ],
            options={
                'db_table': 'posts_brands_classification_judgments',
            },
        ),
        migrations.AddField(
            model_name='postbrandclassificationstate',
            name='selected_final_judgment',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='selected_states', to='core.postbrandclassificationjudgment'),
        ),
        migrations.AddIndex(
            model_name='postbrandclassificationjudgment',
            index=models.Index(fields=['post', 'brand', '-created_at'], name='idx_pb_cls_judgment_history'),
        ),
        migrations.AddIndex(
            model_name='postbrandclassificationjudgment',
            index=models.Index(fields=['revision_id', 'stage'], name='idx_pb_cls_judgment_revision'),
        ),
        migrations.AddConstraint(
            model_name='postbrandclassificationjudgment',
            constraint=models.UniqueConstraint(fields=('post', 'brand', 'revision_id', 'stage'), name='uq_pb_cls_judgment_revision_stage'),
        ),
        migrations.AddConstraint(
            model_name='postbrandclassificationjudgment',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(models.Q(('parent_judgment__isnull', True), ('stage', 'primary')), models.Q(('parent_judgment__isnull', False), ('stage', 'review')), models.Q(('parent_judgment__isnull', False), ('stage', 'final')), _connector='OR')), name='ck_pb_cls_judgment_parent'),
        ),
    ]

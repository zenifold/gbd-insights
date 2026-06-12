from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("runs", "0002_rls_policies")]

    operations = [
        migrations.AddField(
            model_name="analysisrun",
            name="summary",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

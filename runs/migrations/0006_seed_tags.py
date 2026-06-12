from django.db import migrations

DEFAULT_TAGS = [
    ("healthcare", "Healthcare"),
    ("academic", "Academic"),
    ("corporate", "Corporate"),
]


def seed(apps, schema_editor):
    Tag = apps.get_model("runs", "Tag")
    for slug, name in DEFAULT_TAGS:
        Tag.objects.get_or_create(slug=slug, defaults={"name": name})


def unseed(apps, schema_editor):
    Tag = apps.get_model("runs", "Tag")
    Tag.objects.filter(slug__in=[s for s, _ in DEFAULT_TAGS]).delete()


class Migration(migrations.Migration):
    dependencies = [("runs", "0005_tag_analysisrun_tags")]
    operations = [migrations.RunPython(seed, unseed)]

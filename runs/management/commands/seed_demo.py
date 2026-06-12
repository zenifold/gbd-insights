"""Create a demo client so the app is usable immediately after migrate."""
from django.core.management.base import BaseCommand

from runs.db import service_scope
from runs.models import Client


class Command(BaseCommand):
    help = "Seed a demo client."

    def handle(self, *args, **options):
        with service_scope():
            client, created = Client.objects.get_or_create(
                slug="demo-university",
                defaults={"name": "Demo University"},
            )
        verb = "Created" if created else "Already present"
        self.stdout.write(self.style.SUCCESS(f"{verb}: {client.name} ({client.id})"))

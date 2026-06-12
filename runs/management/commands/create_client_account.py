"""
Provision a client self-serve account: a Client org + a login user linked to it.

    python manage.py create_client_account --name "Acme University" \
        --slug acme-university --username acme --password 's3cret'
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from runs.db import service_scope
from runs.models import Client, Profile


class Command(BaseCommand):
    help = "Create a client organization and a login user scoped to it."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--slug", default="")
        parser.add_argument("--username", required=True)
        parser.add_argument("--password", required=True)
        parser.add_argument("--email", default="")

    def handle(self, *args, **o):
        slug = o["slug"] or slugify(o["name"])
        if User.objects.filter(username=o["username"]).exists():
            raise CommandError(f"User {o['username']!r} already exists.")

        with service_scope():
            client, _ = Client.objects.get_or_create(slug=slug, defaults={"name": o["name"]})
            user = User.objects.create_user(
                username=o["username"], password=o["password"], email=o["email"],
                is_staff=False, is_active=True,
            )
            Profile.objects.create(user=user, client=client)

        self.stdout.write(self.style.SUCCESS(
            f"Created client '{client.name}' ({client.slug}) and login '{user.username}'."
        ))

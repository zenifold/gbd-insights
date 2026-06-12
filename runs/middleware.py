"""
Request middleware:

* ``LoginRequiredMiddleware`` — redirects anonymous users to the login page
  (except for a few exempt prefixes and the Django admin, which has its own login).
* ``RLSContextMiddleware`` — wraps each request in a transaction and sets the
  Postgres RLS scope from the logged-in user: GBD staff get the trusted
  service scope (see everything), client users get scoped to their own client.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.db import connection, transaction

from runs.db import set_client_scope, set_service_scope
from runs.scoping import client_id_for, is_gbd_staff


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def _exempt(self, path: str) -> bool:
        if path.startswith("/django-admin"):
            return True  # the admin handles its own authentication
        return any(path.startswith(p) for p in settings.LOGIN_EXEMPT_PREFIXES)

    def __call__(self, request):
        if not request.user.is_authenticated and not self._exempt(request.path):
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        return self.get_response(request)


class RLSContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Storage endpoints carry their own HMAC token and touch no RLS tables.
        if request.path.startswith("/_storage/"):
            return self.get_response(request)
        with transaction.atomic():
            with connection.cursor() as cursor:
                user = getattr(request, "user", None)
                if user is not None and user.is_authenticated:
                    if is_gbd_staff(user):
                        set_service_scope(cursor)
                    else:
                        client_id = client_id_for(user)
                        if client_id is not None:
                            set_client_scope(cursor, client_id)
            return self.get_response(request)

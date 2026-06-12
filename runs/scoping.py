"""
Multi-tenant scoping helpers.

Isolation is enforced at TWO layers:
  1. App level — every run view filters by the user's client (the primary
     guarantee; holds regardless of the DB role).
  2. RLS — the request's GUC scope is set from the user (defense-in-depth; only
     effective when connected as a non-superuser role).
"""
from __future__ import annotations

from django.http import Http404

from runs.models import AnalysisRun


def is_gbd_staff(user) -> bool:
    return bool(user and user.is_authenticated and user.is_staff)


def client_id_for(user):
    """
    The user's client_id WITHOUT querying the (RLS-protected) Client table — reads
    only the FK column on the profile. Used by middleware to set RLS scope before
    any scope exists.
    """
    if not user or not user.is_authenticated:
        return None
    try:
        return user.profile.client_id
    except Exception:
        return None


def client_for(user):
    """The Client a user acts for, or None (GBD staff / unlinked user)."""
    if not user or not user.is_authenticated:
        return None
    try:
        return user.profile.client
    except Exception:
        return None


def visible_runs(user):
    """Runs this user may see: all for GBD staff, else only their client's."""
    qs = AnalysisRun.objects.select_related("client")
    if is_gbd_staff(user):
        return qs
    client = client_for(user)
    if client is None:
        return qs.none()
    return qs.filter(client=client)


def get_run_for(user, run_id) -> AnalysisRun:
    try:
        return visible_runs(user).get(id=run_id)
    except AnalysisRun.DoesNotExist:
        raise Http404("Run not found")

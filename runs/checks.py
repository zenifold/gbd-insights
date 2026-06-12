"""
Deploy-time guards. Run via ``manage.py check --deploy --fail-level ERROR``,
wired into the Render preDeploy step so a misconfigured deploy is blocked before
it can serve traffic.
"""
from django.conf import settings
from django.core.checks import Error, Tags, register

INSECURE_SECRET_KEY = "dev-insecure-change-me"


def insecure_production_defaults(app_configs, **kwargs):
    if settings.DEBUG:
        return []
    errors = []
    if settings.SECRET_KEY == INSECURE_SECRET_KEY:
        errors.append(Error(
            "DJANGO_SECRET_KEY is the insecure development default in production.",
            hint="Set a strong, random DJANGO_SECRET_KEY.",
            id="runs.E001",
        ))
    return errors


def register_checks():
    register(Tags.security, deploy=True)(insecure_production_defaults)

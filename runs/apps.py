from django.apps import AppConfig


class RunsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "runs"

    def ready(self):
        from runs.checks import register_checks

        register_checks()

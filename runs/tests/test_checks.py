from runs.checks import insecure_production_defaults


def test_no_errors_in_debug(settings):
    settings.DEBUG = True
    settings.SECRET_KEY = "dev-insecure-change-me"
    settings.BASIC_AUTH_PASS = "changeme"
    assert insecure_production_defaults(None) == []


def test_flags_insecure_defaults_in_production(settings):
    settings.DEBUG = False
    settings.SECRET_KEY = "dev-insecure-change-me"
    settings.BASIC_AUTH_PASS = "changeme"
    ids = {e.id for e in insecure_production_defaults(None)}
    assert ids == {"runs.E001"}


def test_ok_with_strong_values_in_production(settings):
    settings.DEBUG = False
    settings.SECRET_KEY = "a-very-long-random-production-secret-key-value-123456"
    settings.BASIC_AUTH_PASS = "a-strong-password"
    assert insecure_production_defaults(None) == []

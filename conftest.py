from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent
SAMPLE_CSV = BASE_DIR / "sample_data" / "sample.csv"


@pytest.fixture(autouse=True)
def _storage_tmp(tmp_path_factory, settings):
    """Point the local storage backend at an isolated temp dir per test."""
    settings.STORAGE_BACKEND = "local"
    settings.LOCAL_STORAGE_ROOT = tmp_path_factory.mktemp("storage")
    from runs.storage import get_storage

    get_storage.cache_clear()
    yield
    get_storage.cache_clear()


@pytest.fixture
def sample_csv_bytes():
    return SAMPLE_CSV.read_bytes()

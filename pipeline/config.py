"""Load the data-driven pipeline configuration (taxonomy, factors, units)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

# Bump when the computation logic changes in a way that affects outputs.
PIPELINE_VERSION = "0.1.0"


def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def categories() -> dict:
    return _load("categories.json")


@lru_cache(maxsize=1)
def factors() -> dict:
    return _load("factors.json")


@lru_cache(maxsize=1)
def units() -> dict:
    return _load("units.json")["to_kg"]


def factor_version() -> str:
    return factors().get("version", "unknown")
